import os
import shutil
import subprocess
import zipfile

def package_lambda(name, target_dir=None, dependency_dirs=None, extra_source_dirs=None):
    print(f"Packaging Lambda function: {name}")
    # Root paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lambda_src = os.path.join(base_dir, "lambda", name)
    build_dir = os.path.join(base_dir, "terraform", "build")
    
    # Ensure build dir exists
    os.makedirs(build_dir, exist_ok=True)
    zip_path = os.path.join(build_dir, f"{name}.zip")
    
    # Temporary packaging directory
    tmp_pkg_dir = os.path.join(build_dir, f"tmp_{name}")
    if os.path.exists(tmp_pkg_dir):
        shutil.rmtree(tmp_pkg_dir)
    os.makedirs(tmp_pkg_dir)

    # Copy lambda source file
    shutil.copy2(os.path.join(lambda_src, "index.py"), os.path.join(tmp_pkg_dir, "index.py"))

    for source_dir in extra_source_dirs or []:
        src_path = os.path.join(base_dir, source_dir)
        dst_path = os.path.join(tmp_pkg_dir, os.path.basename(source_dir))
        if os.path.exists(dst_path):
            shutil.rmtree(dst_path)
        shutil.copytree(src_path, dst_path)

    # Install dependencies if specified
    if dependency_dirs:
        for dep in dependency_dirs:
            print(f"  Installing dependency: {dep}")
            try:
                subprocess.check_call([
                    "pip3", "install", dep, "-t", tmp_pkg_dir, "--only-binary=:all:", "--platform", "manylinux2014_x86_64", "--implementation", "cp", "--python-version", "3.12"
                ])
            except Exception as e:
                print(f"  Warning: Platform-specific installation failed ({e}). Falling back to simple pip install.")
                subprocess.check_call([
                    "pip3", "install", dep, "-t", tmp_pkg_dir
                ])

    # Zip the contents of tmp_pkg_dir
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(tmp_pkg_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # Calculate relative path inside the zip file
                arcname = os.path.relpath(file_path, tmp_pkg_dir)
                zipf.write(file_path, arcname)

    # Cleanup temp directory
    shutil.rmtree(tmp_pkg_dir)
    print(f"  Successfully created {zip_path}")

def main():
    # Package each lambda function
    shared = ["lambda/shared"]
    package_lambda("upload", extra_source_dirs=shared)
    package_lambda("list_docs", extra_source_dirs=shared)
    package_lambda("query", extra_source_dirs=shared)
    package_lambda("ingest", dependency_dirs=["pypdf"], extra_source_dirs=shared)
    package_lambda("agent_tool", extra_source_dirs=shared + ["lambda/query"])

if __name__ == "__main__":
    main()
