import os
import fileinput

def replace_api_url():
    # Old and new URLs
    work_dir = os.getcwd()
    package_path = os.path.join(work_dir, ".venv", "Lib", "site-packages", "telebot")
    telebot_dir = os.path.abspath(package_path)

    print(f"Working directory: {work_dir}")
    print(f"Telebot package directory: {telebot_dir}")
    old_url = "https://api.telegram.org/"
    new_url = "https://tapi.bale.ai/"
    
    # Walk through all files in the directory
    for root, dirs, files in os.walk(telebot_dir):
        for file in files:
            if file.endswith('.py'):  # Only process Python files
                filepath = os.path.join(root, file)
                try:
                    # Replace the URL in the file
                    with fileinput.FileInput(filepath, inplace=True, backup='.bak') as file:
                        for line in file:
                            print(line.replace(old_url, new_url), end='')
                    print(f"Processed: {filepath}")
                except Exception as e:
                    print(f"Error processing {filepath}: {str(e)}")
    print("URL replacement completed!")


