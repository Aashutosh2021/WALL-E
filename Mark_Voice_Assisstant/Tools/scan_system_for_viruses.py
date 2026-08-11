import asyncio
import subprocess
from livekit.agents import function_tool

@function_tool()
async def scan_system_for_viruses() -> str:
    """
    Performs quick virus scan using Windows Defender.
    
    Returns:
        str: Scan summary with:
            - Threats found
            - Scan duration
            - Last update
            
    Notes:
        - Requires admin privileges
    """
    import asyncio
    import subprocess

    try:
        cmd = [
            r"C:\Program Files\Windows Defender\MpCmdRun.exe",  # Older path
            "-Scan", "-ScanType", "1"  # 1 = quick scan
        ]

        # fallback path for Windows 10+
        alt_cmd = [
            r"C:\ProgramData\Microsoft\Windows Defender\Platform\4.18.23070.2003-0\MpCmdRun.exe",
            "-Scan", "-ScanType", "1"
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            proc = await asyncio.create_subprocess_exec(
                *alt_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

        stdout, stderr = await proc.communicate()

        output = stdout.decode().strip()
        if "Scan starting" in output or "Scan completed" in output:
            return f"🛡️ सिस्टम स्कैन पूरा हुआ:\n\n{output[-500:]}"
        else:
            return f"⚠️ स्कैन पूरा हुआ, लेकिन कोई जानकारी नहीं मिली:\n\n{output[-500:]}"
        
    except Exception as e:
        return f"❌ स्कैन में त्रुटि: {str(e)}"