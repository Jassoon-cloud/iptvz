from threading import Thread, Lock, Event
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 核心适配：绑定仓库根目录，所有路径自动拼接 ====================
# 自动获取脚本所在的仓库根目录（iptvz），跨环境兼容（本地/云端/GitHub Actions）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 所有子目录（ip/template）、文件都基于仓库根目录创建，无需手动改路径
IP_DIR = os.path.join(BASE_DIR, "ip")
TEMPLATE_DIR = os.path.join(BASE_DIR, "template")

# ==================== 移除全局变量，改为每次扫描时动态创建 ====================
def read_config(config_file):
    print(f"读取设置文件：{config_file}")
    ip_configs = []
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if "," in line and not line.startswith("#"):
                    parts = line.strip().split(',')
                    ip_part, port = parts[0].strip().split(':')
                    a, b, c, d = ip_part.split('.')
                    option = int(parts[1]) 
                    url_end = "/status" if option >= 10 else "/stat"
                    ip = f"{a}.{b}.{c}.1" if option % 2 == 0 else f"{a}.{b}.1.1"
                    ip_configs.append((ip, port, option, url_end))
                    print(f"第{line_num}行：http://{ip}:{port}{url_end}添加到扫描列表")
        return ip_configs
    except Exception as e:
        print(f"读取文件错误: {e}")
        return []

def generate_ip_ports(ip, port, option):
    a, b, c, d = ip.split('.')
    if option == 2 or option == 12:
        c_extent = c.split('-')
        c_first = int(c_extent[0]) if len(c_extent) == 2 else int(c)
        c_last = int(c_extent[1]) + 1 if len(c_extent) == 2 else int(c) + 8
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(c_first, c_last) for y in range(1, 256)]
    elif option == 0 or option == 10:
        return [f"{a}.{b}.{c}.{y}:{port}" for y in range(1, 256)]
    else:  # option=11
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(256) for y in range(1, 256)]

# 核心修改1：check_ip_port不再依赖全局变量，改用参数传递状态
def check_ip_port(ip_port, url_end, option, stop_flag, found_ip, ip_lock, progress_stop_event):    
    # 先检查是否需要停止
    if option == 11 and stop_flag.is_set():
        return None
    
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=3, verify=False, allow_redirects=False)  # 关闭重定向，避免跨网段污染
        resp.raise_for_status()
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            print(f"{url} 访问成功")
            
            if option == 11:
                with ip_lock:
                    found_ip[0] = ip_port  # 用列表（可变对象）存储找到的IP
                stop_flag.set()  # 标记停止
                progress_stop_event.set()  # 终止进度线程
            
            return ip_port
    except Exception as e:
        # 可选：打印失败原因，方便排查
        # print(f"{url} 扫描失败：{str(e)[:50]}")
        return None

# 核心修改2：scan_ip_port内创建所有局部状态，彻底隔离每次扫描
def scan_ip_port(ip, port, option, url_end):
    # 每次扫描都重新创建独立的状态变量，彻底隔离
    stop_flag = Event()  # 替换全局的stop_option_11
    found_ip = [None]    # 用列表存储找到的IP（可变对象）
    ip_lock = Lock()     # 每次扫描新建锁
    progress_stop_event = Event()  # 每次扫描新建进度终止事件
    
    def show_progress(checked, total, stop_flag, progress_stop_event):
        while not progress_stop_event.is_set() and checked[0] < total and (option % 2 == 1) and (not stop_flag.is_set() or option != 11):
            count = 1 if found_ip[0] else 0
            print(f"已扫描：{checked[0]}/{total}, 有效ip_port：{count}个")
            # 每1秒检查一次终止信号
            for _ in range(30):
                if progress_stop_event.is_set() or stop_flag.is_set():
                    return
                time.sleep(1)
    
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    if not ip_ports:
        print(f"⚠️  未生成待扫描IP（{ip}:{port}）")
        return valid_ip_ports
    
    checked = [0]  # 用列表存储已扫描数量（可变对象）
    # 启动进度线程
    progress_thread = Thread(target=show_progress, args=(checked, len(ip_ports), stop_flag, progress_stop_event), daemon=True)
    progress_thread.start()
    
    # 配置并发数
    max_workers = 250 if option % 2 == 1 else 150
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {}
    
    # 提交扫描任务
    for ip_port in ip_ports:
        if option == 11 and stop_flag.is_set():
            break  # 找到有效IP后停止提交新任务
        future = executor.submit(
            check_ip_port, 
            ip_port, url_end, option, 
            stop_flag, found_ip, ip_lock, progress_stop_event  # 传递局部状态，而非全局
        )
        futures[future] = ip_port
    
    try:
        for future in as_completed(futures):
            if option == 11 and stop_flag.is_set():
                # 找到有效IP后，快速处理剩余任务并退出
                try:
                    result = future.result()
                    if result:
                        valid_ip_ports.append(result)
                except:
                    pass
                progress_stop_event.set()
                break
            
            try:
                result = future.result()
                if result:
                    valid_ip_ports.append(result)
                checked[0] += 1
            except Exception as e:
                checked[0] += 1
                continue
    finally:
        # 强制关闭线程池，确保无残留
        executor.shutdown(wait=False, cancel_futures=True)
        # 终止进度线程并等待其退出
        progress_stop_event.set()
        progress_thread.join(timeout=2)
    
    # 处理规则11的结果（只保留第一个有效IP）
    if option == 11:
        if found_ip[0] and found_ip[0] not in valid_ip_ports:
            valid_ip_ports = [found_ip[0]]
        valid_ip_ports = valid_ip_ports[:1]
    
    # 清空所有状态，防止内存泄漏
    stop_flag.clear()
    progress_stop_event.clear()
    
    return valid_ip_ports

def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"\n{'='*50}")
    print(f"开始扫描配置文件：{config_file}")
    print(f"{'='*50}")
    print(f"{'='*25}\n   获取: {province}ip_port\n{'='*25}")
    configs = sorted(set(read_config(config_file)))
    print(f"读取完成，共需扫描 {len(configs)}组")
    all_ip_ports = []
    
    for ip, port, option, url_end in configs:
        print(f"\n开始扫描  http://{ip}:{port}{url_end} (规则{option})")
        # 每次扫描都是独立的，彻底隔离上一次的状态
        scan_result = scan_ip_port(ip, port, option, url_end)
        
        if scan_result:
            all_ip_ports.extend(scan_result)
            if option == 11:
                print(f"✅ 规则{option}找到第一个有效IP：{scan_result[0]}，停止当前组扫描")
            else:
                print(f"✅ 规则{option}扫描完成，找到{len(scan_result)}个有效IP")
        else:
            print(f"❌ 规则{option}未找到有效IP")
    
    if len(all_ip_ports) != 0:
        all_ip_ports = sorted(set(all_ip_ports))
        print(f"\n{province} 扫描完成，获取有效ip_port共：{len(all_ip_ports)}个\n{all_ip_ports}\n")
        
        # 基于仓库根目录创建ip目录，适配权限
        if not os.path.exists(IP_DIR):
            os.makedirs(IP_DIR, mode=0o755)
            print(f"✅ 已创建ip目录：{IP_DIR}")
        
        # 保存有效IP到仓库根目录/ip/下
        ip_save_path = os.path.join(IP_DIR, f"{province}_ip.txt")
        with open(ip_save_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_ip_ports))
        print(f"✅ 有效IP已保存到：{ip_save_path}")
        
        # 存档文件路径适配
        ip_archive_path = os.path.join(IP_DIR, f"存档_{province}_ip.txt")
        if os.path.exists(ip_archive_path):
            with open(ip_archive_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for ip_port in all_ip_ports:
                ip, port = ip_port.split(":")
                a, b, c, d = ip.split(".")
                lines.append(f"{a}.{b}.{c}.1:{port}\n")
            lines = sorted(set(lines))
            with open(ip_archive_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            print(f"✅ 存档文件已更新：{ip_archive_path}")
        
        # 模板文件路径适配（仓库根目录/template/下）
        template_file = os.path.join(TEMPLATE_DIR, f"template_{province}.txt")
        if os.path.exists(template_file):
            with open(template_file, 'r', encoding='utf-8') as f:
                tem_channels = f.read()
            output = [] 
            with open(ip_save_path, 'r', encoding='utf-8') as f:
                for line in f:
                    ip = line.strip()
                    output.append(tem_channels.replace("ipipip", f"{ip}"))
            # 组播文件保存到仓库根目录
            multicast_file = os.path.join(BASE_DIR, f"组播_{province}.txt")
            with open(multicast_file, 'w', encoding='utf-8') as f:
                f.writelines(output)
            print(f"✅ 省份组播文件已生成：{multicast_file}")
        else:
            print(f"⚠️  缺少模板文件，路径：{template_file}（请放到{TEMPLATE_DIR}目录下）")
    else:
        print(f"\n{province} 扫描完成，未扫描到有效ip_port")

def main():
    # 基于仓库根目录创建ip/template子目录，自动适配权限
    for dir_name in [IP_DIR, TEMPLATE_DIR]:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name, mode=0o755)
            print(f"✅ 初始化创建目录：{dir_name}")
    
    # 扫描ip目录下的配置文件（仓库根目录/ip/*_config.txt）
    config_files = glob.glob(os.path.join(IP_DIR, '*_config.txt'))
    if not config_files:
        print(f"⚠️  未找到配置文件！请将*_config.txt放到{IP_DIR}目录下")
        return
    print(f"✅ 找到{len(config_files)}个配置文件，开始批量扫描...\n")
    
    # 扫描每个配置文件前，强制等待1秒，确保所有资源清理完毕
    for config_file in config_files:
        time.sleep(1)  # 防止资源未释放
        multicast_province(config_file)

    # 扫描完成最终提示（无总文件生成）
    print(f"\n🎉 所有省份组播IP扫描完成！")
    print(f"📁 有效IP文件：{IP_DIR}/*_ip.txt")
    print(f"📁 省份组播文件：{BASE_DIR}/组播_*.txt")

if __name__ == "__main__":
    # 禁用requests的HTTPS警告，适配所有环境
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    # 启动主程序
    main()
