import gradio as gr
import os
import xml.etree.ElementTree as ET
import zipfile
from PIL import Image, ImageDraw

# ================= 配置区 =================
# 默认类别列表（用英文逗号分隔）
DEFAULT_CLASSES = "person,car,dog,cat"
# 预设的边界框颜色
COLORS = ["#FF0000", "#0000FF", "#00FF00", "#FFFF00", "#800080", "#FFA500", "#00FFFF", "#FF00FF"]

# ================= 辅助函数 =================
def get_color(idx):
    return COLORS[idx % len(COLORS)]

def parse_classes(class_string):
    return [c.strip() for c in class_string.split(",") if c.strip()]

def load_pascal_voc(img_path):
    """如果存在对应的xml标签文件，则加载它"""
    xml_path = os.path.splitext(img_path)[0] + ".xml"
    boxes = []
    if not os.path.exists(xml_path):
        return boxes
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for obj in root.findall('object'):
            name = obj.find('name').text
            bndbox = obj.find('bndbox')
            xmin = float(bndbox.find('xmin').text)
            ymin = float(bndbox.find('ymin').text)
            xmax = float(bndbox.find('xmax').text)
            ymax = float(bndbox.find('ymax').text)
            boxes.append({'class': name, 'bbox': [xmin, ymin, xmax, ymax]})
    except Exception as e:
        print(f"解析XML失败: {e}")
    return boxes

def prettify_xml(elem, level=0):
    """用于美化生成的 XML，让其带有缩进，和 LabelImg 生成的保持一致"""
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for subelem in elem:
            prettify_xml(subelem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def save_pascal_voc(img_path, boxes, classes):
    """保存为 Pascal VOC XML 格式"""
    if not img_path or not os.path.exists(img_path):
        return "请先加载图片！", None
        
    img = Image.open(img_path)
    w, h = img.size
    xml_path = os.path.splitext(img_path)[0] + ".xml"
    
    # 构建 XML 树
    annotation = ET.Element("annotation")
    ET.SubElement(annotation, "folder").text = "images"
    ET.SubElement(annotation, "filename").text = os.path.basename(img_path)
    ET.SubElement(annotation, "path").text = img_path
    
    source = ET.SubElement(annotation, "source")
    ET.SubElement(source, "database").text = "Unknown"
    
    size = ET.SubElement(annotation, "size")
    ET.SubElement(size, "width").text = str(w)
    ET.SubElement(size, "height").text = str(h)
    ET.SubElement(size, "depth").text = "3"
    
    ET.SubElement(annotation, "segmented").text = "0"
    
    for box in boxes:
        cls_name = box['class']
        if cls_name not in classes:
            continue
        xmin, ymin, xmax, ymax = box['bbox']
        
        obj = ET.SubElement(annotation, "object")
        ET.SubElement(obj, "name").text = cls_name
        ET.SubElement(obj, "pose").text = "Unspecified"
        ET.SubElement(obj, "truncated").text = "0"
        ET.SubElement(obj, "difficult").text = "0"
        
        bndbox = ET.SubElement(obj, "bndbox")
        ET.SubElement(bndbox, "xmin").text = str(int(xmin))
        ET.SubElement(bndbox, "ymin").text = str(int(ymin))
        ET.SubElement(bndbox, "xmax").text = str(int(xmax))
        ET.SubElement(bndbox, "ymax").text = str(int(ymax))
        
    prettify_xml(annotation)
    tree = ET.ElementTree(annotation)
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    
    return f"✅ 成功保存至: {os.path.basename(xml_path)}", xml_path

def draw_annotations(img_path, boxes, classes, clicks=[]):
    """在图片上绘制框和点击点"""
    if not img_path or not os.path.exists(img_path):
        return None
    
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    
    # 画已有的框
    for box in boxes:
        cls_name = box['class']
        xmin, ymin, xmax, ymax = box['bbox']
        cls_idx = classes.index(cls_name) if cls_name in classes else 0
        color = get_color(cls_idx)
        
        draw.rectangle([xmin, ymin, xmax, ymax], outline=color, width=3)
        # 绘制文本背景和文字
        draw.rectangle([xmin, max(0, ymin-15), xmin+len(cls_name)*8+4, max(15, ymin)], fill=color)
        draw.text((xmin+2, max(0, ymin-14)), cls_name, fill="white")

    # 画当前的点击点（提示用户第一个点的位置）
    for cx, cy in clicks:
        r = 6
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill="red", outline="white", width=2)
        # 绘制十字线辅助
        draw.line([cx-15, cy, cx+15, cy], fill="red", width=2)
        draw.line([cx, cy-15, cx, cy+15], fill="red", width=2)
        
    return img

def export_all_xml(images):
    """打包所有生成的 XML 文件提供下载"""
    if not images:
        return None, "没有可导出的文件"
    
    zip_path = "annotations.zip"
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        count = 0
        for img_path in images:
            xml_path = os.path.splitext(img_path)[0] + ".xml"
            if os.path.exists(xml_path):
                zipf.write(xml_path, os.path.basename(xml_path))
                count += 1
                
    if count == 0:
        return None, "尚未保存任何标签文件！"
    return zip_path, f"✅ 成功打包 {count} 个 XML 标签文件。"

# ================= 交互逻辑 =================
def load_uploaded_files(files, class_str):
    if not files:
        return None, [], 0, [], [], "请先选择包含图片的文件夹。"
    
    valid_exts = ('.jpg', '.jpeg', '.png', '.bmp')
    # Gradio 4中 files 是文件路径的列表
    images = [f for f in files if f.lower().endswith(valid_exts)]
    images.sort()
    
    if not images:
        return None, [], 0, [], [], "上传的文件夹中没有找到图片！"
    
    classes = parse_classes(class_str)
    first_img = images[0]
    boxes = load_pascal_voc(first_img)
    drawn_img = draw_annotations(first_img, boxes, classes, [])
    
    return drawn_img, images, 0, boxes, [], f"成功加载，共 {len(images)} 张图片。"

def process_click(evt: gr.SelectData, img_path, boxes, clicks, current_class, class_str):
    if not img_path:
        return None, boxes, clicks
    
    classes = parse_classes(class_str)
    clicks.append((evt.index[0], evt.index[1]))
    
    # 凑齐两个点，生成一个框 (相当于模拟拖拽的起点和终点)
    if len(clicks) == 2:
        x1, y1 = clicks[0]
        x2, y2 = clicks[1]
        xmin, xmax = min(x1, x2), max(x1, x2)
        ymin, ymax = min(y1, y2), max(y1, y2)
        
        # 防止画出极小面积的误触框
        if xmax - xmin > 5 and ymax - ymin > 5:
            boxes.append({
                "class": current_class,
                "bbox": [xmin, ymin, xmax, ymax]
            })
        clicks = [] # 重置点击
        
    rendered_img = draw_annotations(img_path, boxes, classes, clicks)
    return rendered_img, boxes, clicks

def undo_last_box(img_path, boxes, class_str):
    if boxes:
        boxes.pop()
    classes = parse_classes(class_str)
    rendered_img = draw_annotations(img_path, boxes, classes, [])
    return rendered_img, boxes, []

def navigate_image(step, images, current_idx, class_str):
    if not images:
        return None, current_idx, [], [], "没有可用的图片。"
    
    new_idx = current_idx + step
    if new_idx < 0:
        new_idx = 0
    elif new_idx >= len(images):
        new_idx = len(images) - 1
        
    img_path = images[new_idx]
    classes = parse_classes(class_str)
    boxes = load_pascal_voc(img_path)
    rendered_img = draw_annotations(img_path, boxes, classes, [])
    
    return rendered_img, new_idx, boxes, [], f"当前进度: {new_idx + 1} / {len(images)}"

def update_class_radio(class_str):
    classes = parse_classes(class_str)
    return gr.Radio(choices=classes, value=classes[0] if classes else None)

# ================= UI 布局 =================
with gr.Blocks(title="Gradio Web 标注工具") as demo:
    gr.Markdown("## 🎨 极简 Web 目标检测标注工具 (Pascal VOC XML)")
    gr.Markdown("""
    **使用说明**：
    1. 点击 **选择图片文件夹** 并上传你要标注的文件夹。
    2. 在图片上**点击左上角，再点击右下角**（Gradio 限制无法直接拖拽，用两点定框效果完全等同）。
    3. 标好一张后点击 **保存当前标签**，然后下一张。
    4. 标注结束后，点击底部的 **打包下载所有标签** 获取所有的 XML 文件。
    """)
    
    # 状态变量 (隐藏)
    image_list_state = gr.State([])
    current_idx_state = gr.State(0)
    boxes_state = gr.State([])
    clicks_state = gr.State([])
    
    with gr.Row():
        folder_upload = gr.File(label="选择图片文件夹 (自动读取)", file_count="directory", type="filepath", scale=2)
        class_input = gr.Textbox(label="类别 (英文逗号分隔)", value=DEFAULT_CLASSES, scale=1)
        
    with gr.Row():
        with gr.Column(scale=4):
            # 这里的 interactive=False 是防止 Gradio 原生的裁剪框干扰，我们通过 select 事件捕获点击
            image_display = gr.Image(label="工作区 (先点左上顶点，再点右下顶点)", interactive=False, type="filepath")
            
        with gr.Column(scale=1):
            class_radio = gr.Radio(choices=parse_classes(DEFAULT_CLASSES), value=parse_classes(DEFAULT_CLASSES)[0], label="当前选中的类别")
            
            with gr.Row():
                undo_btn = gr.Button("↩️ 撤销上一框")
                save_btn = gr.Button("💾 保存当前 XML", variant="primary")
            
            with gr.Row():
                prev_btn = gr.Button("⬅️ 上一张")
                next_btn = gr.Button("下一张 ➡️")
                
            export_btn = gr.Button("📦 打包下载所有标签", variant="secondary")
            
            status_text = gr.Textbox(label="系统状态", interactive=False)
            download_file = gr.File(label="下载文件区")

    # ================= 事件绑定 =================
    # 更新类别单选框
    class_input.change(update_class_radio, inputs=[class_input], outputs=[class_radio])
    
    # 监听文件夹上传
    folder_upload.upload(
        load_uploaded_files, 
        inputs=[folder_upload, class_input], 
        outputs=[image_display, image_list_state, current_idx_state, boxes_state, clicks_state, status_text]
    )

    # 图片点击画框事件
    def on_click_wrapper(evt: gr.SelectData, images, idx, boxes, clicks, current_class, class_str):
        path = images[idx] if images and 0 <= idx < len(images) else None
        return process_click(evt, path, boxes, clicks, current_class, class_str)

    image_display.select(
        on_click_wrapper,
        inputs=[image_list_state, current_idx_state, boxes_state, clicks_state, class_radio, class_input],
        outputs=[image_display, boxes_state, clicks_state]
    )
    
    # 撤销
    def on_undo_wrapper(images, idx, boxes, class_str):
        path = images[idx] if images and 0 <= idx < len(images) else None
        return undo_last_box(path, boxes, class_str)
        
    undo_btn.click(
        on_undo_wrapper,
        inputs=[image_list_state, current_idx_state, boxes_state, class_input],
        outputs=[image_display, boxes_state, clicks_state]
    )
    
    # 保存 XML
    def on_save_wrapper(images, idx, boxes, class_str):
        path = images[idx] if images and 0 <= idx < len(images) else None
        classes = parse_classes(class_str)
        status, xml_path = save_pascal_voc(path, boxes, classes)
        return status, xml_path
        
    save_btn.click(
        on_save_wrapper,
        inputs=[image_list_state, current_idx_state, boxes_state, class_input],
        outputs=[status_text, download_file]
    )
    
    # 上一张 / 下一张
    prev_btn.click(
        lambda imgs, idx, c_str: navigate_image(-1, imgs, idx, c_str),
        inputs=[image_list_state, current_idx_state, class_input],
        outputs=[image_display, current_idx_state, boxes_state, clicks_state, status_text]
    )
    
    next_btn.click(
        lambda imgs, idx, c_str: navigate_image(1, imgs, idx, c_str),
        inputs=[image_list_state, current_idx_state, class_input],
        outputs=[image_display, current_idx_state, boxes_state, clicks_state, status_text]
    )
    
    # 导出所有 XML ZIP
    export_btn.click(
        export_all_xml,
        inputs=[image_list_state],
        outputs=[download_file, status_text]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)