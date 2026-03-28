import os
import xml.etree.ElementTree as ET

# ================= 配置区 =================
XML_DIR = "path/to/your/xml_folder"  # 你解压出来的 XML 文件夹路径
TXT_DIR = "path/to/your/txt_folder"  # 你想保存 YOLO txt 的文件夹路径
CLASSES = ["person", "car", "dog", "cat"]  # 你的类别列表（顺序必须严格和训练时对应！）
# ==========================================

if not os.path.exists(TXT_DIR):
    os.makedirs(TXT_DIR)

for xml_file in os.listdir(XML_DIR):
    if not xml_file.endswith(".xml"):
        continue
        
    xml_path = os.path.join(XML_DIR, xml_file)
    txt_path = os.path.join(TXT_DIR, xml_file.replace(".xml", ".txt"))
    
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    size = root.find('size')
    w = int(size.find('width').text)
    h = int(size.find('height').text)
    
    with open(txt_path, "w") as out_file:
        for obj in root.iter('object'):
            cls_name = obj.find('name').text
            if cls_name not in CLASSES:
                continue
            cls_id = CLASSES.index(cls_name)
            
            xmlbox = obj.find('bndbox')
            xmin = float(xmlbox.find('xmin').text)
            xmax = float(xmlbox.find('xmax').text)
            ymin = float(xmlbox.find('ymin').text)
            ymax = float(xmlbox.find('ymax').text)
            
            # 转换为 YOLO 的归一化中心点格式
            x_center = ((xmin + xmax) / 2) / w
            y_center = ((ymin + ymax) / 2) / h
            width = (xmax - xmin) / w
            height = (ymax - ymin) / h
            
            out_file.write(f"{cls_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")

print("✅ XML 到 YOLO TXT 转换完成！")