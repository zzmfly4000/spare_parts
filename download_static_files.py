import os
import requests


def download_static_files():
    """下载静态文件到本地"""

    # 创建目录结构
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    os.makedirs('static/fonts', exist_ok=True)

    # Bootstrap 5.3.2
    bootstrap_files = {
        'css': 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
        'js': 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
        'icons': 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css'
    }

    # Font Awesome 6.4.0
    font_awesome_files = {
        'css': 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
        'webfonts': [
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-brands-400.woff2',
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-regular-400.woff2',
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.woff2',
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-v4compatibility.woff2'
        ]
    }

    print("正在下载 Bootstrap 文件...")
    for file_type, url in bootstrap_files.items():
        try:
            response = requests.get(url)
            if response.status_code == 200:
                if file_type == 'css':
                    with open('static/css/bootstrap.min.css', 'wb') as f:
                        f.write(response.content)
                    print("✓ 下载 Bootstrap CSS 完成")
                elif file_type == 'js':
                    with open('static/js/bootstrap.bundle.min.js', 'wb') as f:
                        f.write(response.content)
                    print("✓ 下载 Bootstrap JS 完成")
                elif file_type == 'icons':
                    with open('static/css/bootstrap-icons.css', 'wb') as f:
                        f.write(response.content)
                    print("✓ 下载 Bootstrap Icons 完成")
        except Exception as e:
            print(f"✗ 下载 {file_type} 失败: {str(e)}")

    print("\n正在下载 Font Awesome 文件...")
    try:
        # 下载 Font Awesome CSS
        response = requests.get(font_awesome_files['css'])
        if response.status_code == 200:
            css_content = response.text

            # 修改字体路径为本地
            css_content = css_content.replace(
                'src: url("../webfonts/',
                'src: url("/static/fonts/'
            )

            with open('static/css/font-awesome.min.css', 'w', encoding='utf-8') as f:
                f.write(css_content)
            print("✓ 下载 Font Awesome CSS 完成")

            # 下载字体文件
            for font_url in font_awesome_files['webfonts']:
                try:
                    font_response = requests.get(font_url)
                    if font_response.status_code == 200:
                        font_filename = os.path.basename(font_url)
                        with open(f'static/fonts/{font_filename}', 'wb') as f:
                            f.write(font_response.content)
                        print(f"✓ 下载字体 {font_filename} 完成")
                except Exception as e:
                    print(f"✗ 下载字体失败: {str(e)}")
    except Exception as e:
        print(f"✗ 下载 Font Awesome 失败: {str(e)}")

    print("\n✅ 所有静态文件下载完成！")


if __name__ == '__main__':
    download_static_files()