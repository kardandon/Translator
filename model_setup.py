import argparse
import argostranslate.package
import argostranslate.translate
import os

def install_language(from_code, to_code):
    """
    Downloads and installs the translation package for the specified language pair.
    Skips if already installed.
    """
    print(f"Initializing setup for {from_code} -> {to_code}...")
    
    # 1. Check if package is ALREADY installed
    try:
        installed_packages = argostranslate.package.get_installed_packages()
        for pkg in installed_packages:
            if pkg.from_code == from_code and pkg.to_code == to_code:
                print(f"✔ Package {from_code}->{to_code} is already installed. Skipping download.")
                return
    except Exception as e:
        print(f"Warning checking installed packages: {e}")

    # 2. Update index only if we need to install
    print("Updating package index...")
    argostranslate.package.update_package_index()
    
    # 3. Find the package in the available list
    available_packages = argostranslate.package.get_available_packages()
    package_to_install = next(
        (pkg for pkg in available_packages 
         if pkg.from_code == from_code and pkg.to_code == to_code), 
        None
    )
    
    # 4. Install
    if package_to_install:
        print(f"Downloading and installing: {package_to_install}...")
        try:
            download_path = package_to_install.download()
            argostranslate.package.install_from_path(download_path)
            print(f"Successfully installed {from_code} -> {to_code}")
        except Exception as e:
             print(f"Critical error during installation: {e}")
             if 'download_path' in locals() and os.path.exists(download_path):
                 os.remove(download_path)
    else:
        print(f"Error: No package found for {from_code} -> {to_code}")
        print("Available codes usually include: en, es, fr, de, it, pt, ru, zh, ar, tr, etc.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Install Argos Translate Models')
    parser.add_argument('--from_code', type=str, required=True, help='Source language code (e.g., "en")')
    parser.add_argument('--to_code', type=str, required=True, help='Target language code (e.g., "es")')
    
    args = parser.parse_args()
    install_language(args.from_code, args.to_code)