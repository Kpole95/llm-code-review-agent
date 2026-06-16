import zipfile
import os
 
 
def extract_archive(zip_path, output_dir):
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            # No validation: member could be "../../etc/passwd"
            target = os.path.join(output_dir, member)
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
