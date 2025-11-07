
import json
import os

def get_config_for_env(environment='testing'):
    """
    Tải và trả về cấu hình từ file JSON tương ứng với môi trường.

    Args:
        environment (str): Môi trường cần tải cấu hình ('testing' hoặc 'production').

    Returns:
        dict: Từ điển chứa cấu hình, hoặc None nếu có lỗi.
    """
    try:
        # Xác định đường dẫn đến thư mục gốc của dự án (nơi chứa 'src', 'production', 'testing')
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

        # Xây dựng đường dẫn đến file config dựa trên môi trường
        config_filename = f"{environment}_config.json"
        config_path = os.path.join(project_root, 'configs', config_filename)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError as e:
        print(f"Lỗi: Không tìm thấy file cấu hình cho môi trường '{environment}' tại '{config_path}'.")
        print(f"Chi tiết lỗi: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Lỗi: File cấu hình '{config_path}' không phải là file JSON hợp lệ.")
        return None
    except Exception as e:
        print(f"Lỗi không xác định khi tải cấu hình: {e}")
        return None

# Giữ lại hàm get_config cũ để tương thích ngược (mặc định là testing)
get_config = get_config_for_env
