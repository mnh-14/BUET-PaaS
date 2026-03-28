import argparse
import subprocess
import sys
import platform
import time
import re
import tempfile
import os
import dotenv

dotenv.load_dotenv()

CLOUDFLARED_EXECUTABLE = os.getenv("CLOUDFLARED_EXECUTABLE", "D:\\Softwares\\Cloudflared\\cloudflared-windows-amd64.exe")  # Default to 'cloudflared' in PATH


def stop_tunnels1():
    """Kills all running cloudflared processes across Windows and Linux."""
    system = platform.system().lower()
    
    try:
        if system == "windows":
            subprocess.run(["taskkill", "/IM", "cloudflared-windows-amd64", "/F"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["pkill", "-f", "cloudflared"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"Error stopping tunnels: {e}")
        return False

def stop_tunnels2():
    """Kills all running cloudflared processes using tasklist and PID lookup."""
    system = platform.system().lower()
    
    try:
        if system == "windows":
            cmd = 'tasklist /FI "IMAGENAME eq cloudflared" /NH'
            result = subprocess.check_output(cmd, shell=True, text=True)
            
            pids = re.findall(r"cloudflared\s+(\d+)", result)
            
            if not pids:
                print("No running cloudflared tunnels found.")
                return True

            for pid in pids:
                subprocess.run(["taskkill", "/F", "/PID", pid], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"Stopped tunnel with PID: {pid}")
                
        else:
            # Linux equivalent using pgrep/pkill
            subprocess.run(["pkill", "-f", "cloudflared"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"Error stopping tunnels: {e}")
        return False


def stop_tunnels():
    """Kills all running cloudflared processes using tasklist | findstr logic."""
    system = platform.system().lower()
    
    try:
        if system == "windows":
            # Running the exact command you wanted
            # shell=True is mandatory here to make the pipe '|' work
            cmd = 'tasklist | findstr cloudflared'
            
            try:
                result = subprocess.check_output(cmd, shell=True, text=True)
            except subprocess.CalledProcessError:
                print("No running cloudflared processes found.")
                return True
            
            # Extract PIDs from the output
            # findstr output looks like: cloudflared.exe   1234 Console  1  10,000 K
            # We look for the first number following the .exe name
            pids = re.findall(r"cloudflared\.exe\s+(\d+)", result)
            
            if not pids:
                print("Could not parse PIDs from tasklist.")
                return False

            for pid in pids:
                print(f"Killing PID: {pid}")
                subprocess.run(["taskkill", "/F", "/PID", pid], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
        else:
            # Linux backup
            subprocess.run(["pkill", "-f", "cloudflared"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def stop_tunnels():
    """Kills all running cloudflared processes using tasklist | findstr logic."""
    system = platform.system().lower()
    
    try:
        if system == "windows":
            # Running the exact command you wanted
            # shell=True is mandatory here to make the pipe '|' work
            cmd = 'tasklist | findstr cloudflared'
            
            try:
                result = subprocess.check_output(cmd, shell=True, text=True)
            except subprocess.CalledProcessError:
                print("No running cloudflared processes found.")
                return True
            
            # Extract PIDs from the output
            # findstr output looks like: cloudflared.exe   1234 Console  1  10,000 K
            # We look for the first number following the .exe name
            print(result)
            tasks = result.strip().splitlines()
            pids = [task.split()[1] for task in tasks if "cloudflared" in task]
            # for task in tasks:
            #     print(f"Task: {task.split()[1]}")
            # pids = re.findall(r"cloudflared\.exe\s+(\d+)", result)
            
            if not pids:
                print("Could not parse PIDs from tasklist.")
                return False

            for pid in pids:
                print(f"Killing PID: {pid}")
                subprocess.run(["taskkill", "/F", "/PID", pid], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
        else:
            # Linux backup
            subprocess.run(["pkill", "-f", "cloudflared"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False



def start_tunnel(target):
    """
    Starts a detached cloudflared tunnel, extracts the URL, and returns it.
    Returns the URL as a string if successful, or None if it fails.
    """
    system = platform.system().lower()
    log_file = tempfile.NamedTemporaryFile(delete=False, suffix="_cloudflared.log").name
    cmd = [CLOUDFLARED_EXECUTABLE, "tunnel", "--url", target]
    
    try:
        f_out = open(log_file, "w")
        
        # Spawn the process detached from the parent console
        if system == "windows":
            p = subprocess.Popen(cmd, stdout=f_out, stderr=f_out, creationflags=0x00000008)
        else:
            p = subprocess.Popen(cmd, stdout=f_out, stderr=f_out, start_new_session=True)
            
        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        start_time = time.time()
        url = None
        timeout = 20 

        # Tail the log file to find the trycloudflare URL
        with open(log_file, "r") as f_in:
            while time.time() - start_time < timeout:
                line = f_in.readline()
                if not line:
                    time.sleep(0.5) 
                    continue
                
                match = url_pattern.search(line)
                if match:
                    url = match.group(0)
                    break
        
        # Optionally clean up the log file here if you want
        if url:
             try:
                 os.remove(log_file)
             except OSError:
                 pass
                 
        return url
            
    except FileNotFoundError:
        print("Error: 'cloudflared' is not recognized. Please check your PATH.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Cloudflared Quick Tunnel Background Manager")
    parser.add_argument("--port", type=str, help="Port to tunnel (e.g., 8080)")
    parser.add_argument("--url", type=str, help="Complete URL to tunnel (e.g., http://localhost:8080)")
    parser.add_argument("--stop", action="store_true", help="Stop all running cloudflared tunnels")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    if args.stop:
        print("Attempting to stop all cloudflared processes...")
        if stop_tunnels():
            print("Success: All cloudflared tunnels have been stopped.")
    else:
        url = None
        if args.port:
            print(f"Starting tunnel for localhost:{args.port}...")
            url = start_tunnel(f"localhost:{args.port}")
        elif args.url:
            print(f"Starting tunnel for {args.url}...")
            url = start_tunnel(args.url)
        
        if url:
            print(f"\n[+] Tunnel successfully established!")
            print(f"[+] URL: {url}\n")
            print("You can safely close this terminal. The tunnel will continue running in the background.")
        else:
            print("\n[-] Failed to extract the URL or start the tunnel.")

if __name__ == "__main__":
    main()