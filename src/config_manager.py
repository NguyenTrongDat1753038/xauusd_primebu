
import json
import os

def get_config_by_name(config_name='testing_config'):
    """
    Tải và trả về cấu hình từ file JSON được chỉ định theo tên.

    Args:
        config_name (str): Tên của file cấu hình (không bao gồm .json).

    Returns:
        dict: Từ điển chứa cấu hình, hoặc None nếu có lỗi.
    """
    try:
        # Xác định đường dẫn đến thư mục gốc của dự án (nơi chứa 'src', 'production', 'testing')
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

        # Xây dựng đường dẫn đến file config dựa trên môi trường
        config_filename = f"{config_name}.json"
        config_path = os.path.join(project_root, 'configs', config_filename)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError as e:
        print(f"Lỗi: Không tìm thấy file cấu hình có tên '{config_name}' tại '{config_path}'.")
        print(f"Chi tiết lỗi: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Lỗi: File cấu hình '{config_path}' không phải là file JSON hợp lệ.")
        return None
    except Exception as e:
        print(f"Lỗi không xác định khi tải cấu hình: {e}")
        return None

# Đổi tên hàm cũ để rõ ràng hơn, nhưng vẫn giữ hàm get_config để tương thích
get_config = lambda: get_config_by_name('production_config') # Giả sử mặc định là file này
