import os
import re
import sys
import subprocess
from datetime import datetime, timedelta

# 杂志配置信息
MAGZINES = {
    "ny": {
        "id": "ny",
        "name": "The New Yorker Magazine",
        "recipe": "The New Yorker Magazine",
        "folder": "the_new_yorker",
        "date_regex": r"magazine/\K\d{4}/\d{2}/\d{2}",
    },
    "te": {
        "id": "te",
        "name": "The Economist",
        "recipe": "The Economist",
        "folder": "the_economist",
        "date_regex": r"images/\K(\d{8})",
    },
    # ===== 修改：tm 使用自定义 Recipe 以压缩图片 =====
    "tm": {
        "id": "tm",
        "name": "TIME Magazine",
        "recipe": "time_custom",  # 改为自定义 Recipe
        "folder": "time_magzine",
        "date_regex": r"TIM\K(\d{6})",
    },
}

RECIPE_OPTIONS = {
    "te": "date",
    "ny": "date",
    "tm": "edition",
}

BOOKS_DIR = "converted_ebooks"

def extract_date_from_output(output, mag_id):
    config = MAGZINES[mag_id]
    regex = config.get("date_regex")
    if not regex:
        return None
    
    if mag_id == "ny":
        match = re.search(r"magazine/(\d{4})/(\d{2})/(\d{2})", output)
        if match:
            return "".join(match.groups())
    elif mag_id == "te":
        match = re.search(r"images/(\d{8})", output)
        if match:
            return match.group(1)
    elif mag_id == "tm":
        match = re.search(r"TIM(\d{6})", output)
        if match:
            return f"20{match.group(1)}"
    return None

def extract_date_from_file(filename):
    match = re.search(r"\[([A-Za-z]+)\s(\d{1,2})(?:st|nd|rd|th)?(?:,\s(\d{4}))?\]", filename)
    if match:
        month_str, day, year = match.groups()
        try:
            month = datetime.strptime(month_str[:3], "%b").month
        except:
            return None
        if not year:
            year = datetime.now().year
        return f"{year}{int(month):02d}{int(day):02d}"
    return None

def run_command(args):
    print(f"Running: {' '.join(args)}")
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
    
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    full_output = []
    if process.stdout:
        for line in process.stdout:
            print(line, end="")
            full_output.append(line)
    process.wait()
    return "".join(full_output), process.returncode

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <mag_id>")
        sys.exit(1)

    mag_id = sys.argv[1]
    if mag_id not in MAGZINES:
        print(f"Unknown magazine: {mag_id}")
        sys.exit(1)

    issue_date = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] and sys.argv[2] != "." else None

    if (mag_id == "te" or mag_id == "ny") and issue_date:
        try:
            clean_date = issue_date.replace("-", "").replace("/", "")
            dt_obj = datetime.strptime(clean_date, "%Y%m%d")
            
            if mag_id == "te":
                offset = (dt_obj.weekday() + 2) % 7
                target_fmt = "%Y-%m-%d"
                day_name = "Saturday"
            else:
                offset = dt_obj.weekday()
                target_fmt = "%Y/%m/%d"
                day_name = "Monday"

            if offset > 0:
                dt_obj = dt_obj - timedelta(days=offset)
                old_date = issue_date
                issue_date = dt_obj.strftime(target_fmt)
                print(f"Adjusted date for {mag_id}: {old_date} -> {issue_date} ({day_name})")
            else:
                issue_date = dt_obj.strftime(target_fmt)
        except Exception as e:
            print(f"Warning: Failed to auto-adjust date: {e}")

    config = MAGZINES[mag_id]
    recipe = config["recipe"]
    
    if not os.path.exists(BOOKS_DIR):
        os.makedirs(BOOKS_DIR)

    try:
        ip_info = subprocess.check_output(["curl", "-s", "https://ifconfig.me"], text=True).strip()
        print(f"Current Public IP: {ip_info}")
    except:
        pass

    print(f"--- Fetching {config['name']} ---")
    raw_epub = "temp_output.epub"
    
    convert_args = ["ebook-convert", f"{recipe}.recipe", raw_epub]
    
    if issue_date:
        opt_name = RECIPE_OPTIONS.get(mag_id, "date")
        convert_args.append(f"--recipe-specific-option={opt_name}:{issue_date}")
        print(f"Using recipe option: {opt_name}:{issue_date}")

    convert_output, code = run_command(convert_args)
    
    if code != 0 or not os.path.exists(raw_epub):
        print("Conversion failed.")
        sys.exit(1)

    date_str = extract_date_from_output(convert_output, mag_id)
        
    if not date_str:
        date_str = extract_date_from_file(raw_epub)

    if not date_str and issue_date:
        date_str = issue_date.replace("-", "")
        print(f"Extraction failed, using specified date as fallback: {date_str}")
    
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")
        print(f"Warning: Could not extract date, using current: {date_str}")
    
    print(f"Publication Date: {date_str}")

    base_name = f"{date_str} - {config['name']}"
    target_dir = os.path.join(BOOKS_DIR, date_str)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    final_epub = os.path.join(target_dir, f"{base_name}.epub")
    final_pdf = os.path.join(target_dir, f"{base_name}.pdf")
    cover_jpg = os.path.join(target_dir, "cover.jpg")

    os.rename(raw_epub, final_epub)

    run_command(["ebook-meta", final_epub, f"--get-cover={cover_jpg}"])

    print(f"Converting to PDF...")
    run_command(["ebook-convert", final_epub, final_pdf])

    if "GITHUB_ENV" in os.environ:
        with open(os.environ["GITHUB_ENV"], "a") as f:
            f.write(f"DATE={date_str}\n")
            f.write(f"MAG_FOLDER={config['folder']}\n")
            f.write(f"MAG_NAME={config['name']}\n")

    print(f"Success! Files saved in {target_dir}")

if __name__ == "__main__":
    main()
