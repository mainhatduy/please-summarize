"""
Kinh Dịch Service – Rút quẻ Kinh Dịch và luận giải bằng AI
============================================================
Dữ liệu 64 quẻ dịch lấy từ nguồn: https://dich.kabala.vn/kinh-dich/
Mỗi quẻ gồm: số, tên đầy đủ, tên ngắn, Hán tự, ngoại quái, nội quái,
nhóm tượng, ngũ hành, mức cát/hung, và triệu (lời đoán).
"""

import logging
import random
import re
import time
import hashlib
import httpx
from google import genai
from app.core.config import Config

log = logging.getLogger("bot.kinhdich")

# ── 64 Quẻ Kinh Dịch ─────────────────────────────────────────────────────────
HEXAGRAMS = [
    {
        "so": 1, "ten": "Thiên Vi Càn", "ten_ngan": "Càn", "han_tu": "乾",
        "ngoai_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "noi_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "nhom_tuong": "Càn", "ngu_hanh": "Kim",
        "muc": "Đại Cát", "trieu": "Khốn Long Đắc Thủy - Thời Vận Đã Đến",
        "slug": "thien-vi-can",
    },
    {
        "so": 2, "ten": "Địa Vi Khôn", "ten_ngan": "Khôn", "han_tu": "坤",
        "ngoai_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "noi_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "nhom_tuong": "Khôn", "ngu_hanh": "Thổ",
        "muc": "Đại Cát", "trieu": "Ngạ Hổ Đắc Thực - Thỏa lòng mãn ý",
        "slug": "dia-vi-khon",
    },
    {
        "so": 3, "ten": "Thủy Lôi Truân", "ten_ngan": "Truân", "han_tu": "屯",
        "ngoai_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "noi_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "nhom_tuong": "Khảm", "ngu_hanh": "Thủy",
        "muc": "Hung", "trieu": "Loạn Ti Vô Đầu - Lòng Dạ Rối Bời",
        "slug": "thuy-loi-truan",
    },
    {
        "so": 4, "ten": "Sơn Thủy Mông", "ten_ngan": "Mông", "han_tu": "蒙",
        "ngoai_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "noi_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "nhom_tuong": "Ly", "ngu_hanh": "Hỏa",
        "muc": "Hung", "trieu": "Tiểu Quỷ Thâu Tiền - Thời vận không hay",
        "slug": "son-thuy-mong",
    },
    {
        "so": 5, "ten": "Thủy Thiên Nhu", "ten_ngan": "Nhu", "han_tu": "需",
        "ngoai_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "noi_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "nhom_tuong": "Khôn", "ngu_hanh": "Thổ",
        "muc": "Cát", "trieu": "Minh Châu Xuất Thổ - Vận tốt đã đến",
        "slug": "thuy-thien-nhu",
    },
    {
        "so": 6, "ten": "Thiên Thủy Tụng", "ten_ngan": "Tụng", "han_tu": "訟",
        "ngoai_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "noi_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "nhom_tuong": "Ly", "ngu_hanh": "Hỏa",
        "muc": "Hung", "trieu": "Nhị Nhân Tranh Lộ - Việc làm không thuận",
        "slug": "thien-thuy-tung",
    },
    {
        "so": 7, "ten": "Địa Thủy Sư", "ten_ngan": "Sư", "han_tu": "師",
        "ngoai_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "noi_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "nhom_tuong": "Khảm", "ngu_hanh": "Thủy",
        "muc": "Cát", "trieu": "Mã Đáo Thành Công - Mọi sự tốt đẹp",
        "slug": "dia-thuy-su",
    },
    {
        "so": 8, "ten": "Thủy Địa Tỷ", "ten_ngan": "Tỷ", "han_tu": "比",
        "ngoai_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "noi_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "nhom_tuong": "Khôn", "ngu_hanh": "Thổ",
        "muc": "Cát", "trieu": "Thuận Phong Hành Thuyền - Việc gì cũng lợi",
        "slug": "thuy-dia-ty",
    },
    {
        "so": 9, "ten": "Phong Thiên Tiểu Súc", "ten_ngan": "Tiểu Súc", "han_tu": "小畜",
        "ngoai_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "noi_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "nhom_tuong": "Tốn", "ngu_hanh": "Mộc",
        "muc": "Bình Hòa", "trieu": "Mật Vân Bất Vũ - Tạm thời phải nhẫn",
        "slug": "phong-thien-tieu-suc",
    },
    {
        "so": 10, "ten": "Thiên Trạch Lý", "ten_ngan": "Lý", "han_tu": "履",
        "ngoai_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "noi_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "nhom_tuong": "Cấn", "ngu_hanh": "Thổ",
        "muc": "Cát", "trieu": "Phượng Minh Kỳ Sơn - Quốc gia cát tường",
        "slug": "thien-trach-ly",
    },
    {
        "so": 11, "ten": "Địa Thiên Thái", "ten_ngan": "Thái", "han_tu": "泰",
        "ngoai_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "noi_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "nhom_tuong": "Khôn", "ngu_hanh": "Thổ",
        "muc": "Cát", "trieu": "Hỷ Báo Tam Nguyên - Đại cát đại lợi",
        "slug": "dia-thien-thai",
    },
    {
        "so": 12, "ten": "Thiên Địa Bĩ", "ten_ngan": "Bĩ", "han_tu": "否",
        "ngoai_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "noi_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "nhom_tuong": "Càn", "ngu_hanh": "Kim",
        "muc": "Hung", "trieu": "Hổ Lạc Hãm Khanh - Cát ít hung nhiều",
        "slug": "thien-dia-bi",
    },
    {
        "so": 13, "ten": "Thiên Hỏa Đồng Nhân", "ten_ngan": "Đồng Nhân", "han_tu": "同人",
        "ngoai_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "noi_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "nhom_tuong": "Ly", "ngu_hanh": "Hỏa",
        "muc": "Cát", "trieu": "Tiên Nhân Chỉ Lộ - Đi đâu cũng lợi",
        "slug": "thien-hoa-dong-nhan",
    },
    {
        "so": 14, "ten": "Hỏa Thiên Đại Hữu", "ten_ngan": "Đại Hữu", "han_tu": "大有",
        "ngoai_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "noi_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "nhom_tuong": "Càn", "ngu_hanh": "Kim",
        "muc": "Đại Cát", "trieu": "Nhuyễn Mộc Nô Tước - Làm việc chắc chắn",
        "slug": "hoa-thien-dai-huu",
    },
    {
        "so": 15, "ten": "Địa Sơn Khiêm", "ten_ngan": "Khiêm", "han_tu": "謙",
        "ngoai_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "noi_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "nhom_tuong": "Đoài", "ngu_hanh": "Kim",
        "muc": "Cát", "trieu": "Nhị Nhân Phân Kim - Vạn sự hanh thông",
        "slug": "dia-son-khiem",
    },
    {
        "so": 16, "ten": "Lôi Địa Dự", "ten_ngan": "Dự", "han_tu": "豫",
        "ngoai_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "noi_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "nhom_tuong": "Chấn", "ngu_hanh": "Mộc",
        "muc": "Cát", "trieu": "Thanh Long Đắc Vị - Gặp hung hóa cát",
        "slug": "loi-dia-du",
    },
    {
        "so": 17, "ten": "Trạch Lôi Tùy", "ten_ngan": "Tùy", "han_tu": "隨",
        "ngoai_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "noi_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "nhom_tuong": "Chấn", "ngu_hanh": "Mộc",
        "muc": "Bình Hòa", "trieu": "Bộ Bộ Đăng Cao - Lên cao từng bước",
        "slug": "trach-loi-tuy",
    },
    {
        "so": 18, "ten": "Sơn Phong Cổ", "ten_ngan": "Cổ", "han_tu": "蠱",
        "ngoai_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "noi_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "nhom_tuong": "Tốn", "ngu_hanh": "Mộc",
        "muc": "Hung", "trieu": "Thôi Ma Phần Đạo - Làm không đúng cách",
        "slug": "son-phong-co",
    },
    {
        "so": 19, "ten": "Địa Trạch Lâm", "ten_ngan": "Lâm", "han_tu": "臨",
        "ngoai_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "noi_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "nhom_tuong": "Khôn", "ngu_hanh": "Thổ",
        "muc": "Bình Hòa", "trieu": "Phát Chánh Thi Nhân - Thời vận hanh thông",
        "slug": "dia-trach-lam",
    },
    {
        "so": 20, "ten": "Phong Địa Quán", "ten_ngan": "Quán", "han_tu": "觀",
        "ngoai_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "noi_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "nhom_tuong": "Càn", "ngu_hanh": "Kim",
        "muc": "Bình Hòa", "trieu": "Hạn Bồng Phùng Hà - Quý nhân phù trợ",
        "slug": "phong-dia-quan",
    },
    {
        "so": 21, "ten": "Hỏa Lôi Phệ Hạp", "ten_ngan": "Phệ Hạp", "han_tu": "噬嗑",
        "ngoai_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "noi_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "nhom_tuong": "Tốn", "ngu_hanh": "Mộc",
        "muc": "Bình Hòa", "trieu": "Cô Nhân Ngộ Thực - Gặp may gặp mắn",
        "slug": "hoa-loi-phe-hap",
    },
    {
        "so": 22, "ten": "Sơn Hỏa Bí", "ten_ngan": "Bí", "han_tu": "賁",
        "ngoai_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "noi_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "nhom_tuong": "Cấn", "ngu_hanh": "Thổ",
        "muc": "Cát", "trieu": "Hỷ Khí Doanh Môn - Vạn sự như ý",
        "slug": "son-hoa-bi",
    },
    {
        "so": 23, "ten": "Sơn Địa Bác", "ten_ngan": "Bác", "han_tu": "剝",
        "ngoai_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "noi_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "nhom_tuong": "Càn", "ngu_hanh": "Kim",
        "muc": "Hung", "trieu": "Ưng Thước Đồng Lâm - Việc không thành",
        "slug": "son-dia-bac",
    },
    {
        "so": 24, "ten": "Địa Lôi Phục", "ten_ngan": "Phục", "han_tu": "復",
        "ngoai_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "noi_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "nhom_tuong": "Khôn", "ngu_hanh": "Thổ",
        "muc": "Bình Hòa", "trieu": "Phu Thê Phản Mục - Tráo trở lật lọng",
        "slug": "dia-loi-phuc",
    },
    {
        "so": 25, "ten": "Thiên Lôi Vô Vọng", "ten_ngan": "Vô Vọng", "han_tu": "無妄",
        "ngoai_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "noi_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "nhom_tuong": "Tốn", "ngu_hanh": "Mộc",
        "muc": "Hung", "trieu": "Điểu Bị Lao Lung - Tù túng buồn lo",
        "slug": "thien-loi-vo-vong",
    },
    {
        "so": 26, "ten": "Sơn Thiên Đại Súc", "ten_ngan": "Đại Súc", "han_tu": "大畜",
        "ngoai_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "noi_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "nhom_tuong": "Cấn", "ngu_hanh": "Thổ",
        "muc": "Cát", "trieu": "Trận Thế Đắc Khai - Không còn trở ngại",
        "slug": "son-thien-dai-suc",
    },
    {
        "so": 27, "ten": "Sơn Lôi Di", "ten_ngan": "Di", "han_tu": "頤",
        "ngoai_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "noi_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "nhom_tuong": "Tốn", "ngu_hanh": "Mộc",
        "muc": "Cát Hanh", "trieu": "Vị Thủy Phỏng Hiền - Bĩ cực thái lai",
        "slug": "son-loi-di",
    },
    {
        "so": 28, "ten": "Trạch Phong Đại Quá", "ten_ngan": "Đại Quá", "han_tu": "大過",
        "ngoai_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "noi_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "nhom_tuong": "Chấn", "ngu_hanh": "Mộc",
        "muc": "Cát", "trieu": "Dạ Mộng Kim Ngân - Không vẫn hoàn không",
        "slug": "trach-phong-dai-qua",
    },
    {
        "so": 29, "ten": "Thủy Vi Khảm", "ten_ngan": "Khảm", "han_tu": "坎",
        "ngoai_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "noi_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "nhom_tuong": "Khảm", "ngu_hanh": "Thủy",
        "muc": "Bình Hòa", "trieu": "Thủy Để Lao Nguyệt - Uổng công phí sức",
        "slug": "thuy-vi-kham",
    },
    {
        "so": 30, "ten": "Hỏa Vi Ly", "ten_ngan": "Ly", "han_tu": "離",
        "ngoai_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "noi_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "nhom_tuong": "Ly", "ngu_hanh": "Hỏa",
        "muc": "Cát", "trieu": "Thiên Quan Tứ Phước - Phát phúc sinh tài",
        "slug": "hoa-vi-ly",
    },
    {
        "so": 31, "ten": "Trạch Sơn Hàm", "ten_ngan": "Hàm", "han_tu": "咸",
        "ngoai_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "noi_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "nhom_tuong": "Đoài", "ngu_hanh": "Kim",
        "muc": "Cát", "trieu": "Manh Nha Xuất Thổ - Thời vận đã đến",
        "slug": "trach-son-ham",
    },
    {
        "so": 32, "ten": "Lôi Phong Hằng", "ten_ngan": "Hằng", "han_tu": "恆",
        "ngoai_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "noi_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "nhom_tuong": "Chấn", "ngu_hanh": "Mộc",
        "muc": "Cát", "trieu": "Ngư Lai Trành Võng - Vạn sự như ý",
        "slug": "loi-phong-hang",
    },
    {
        "so": 33, "ten": "Thiên Sơn Độn", "ten_ngan": "Độn", "han_tu": "遯",
        "ngoai_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "noi_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "nhom_tuong": "Càn", "ngu_hanh": "Kim",
        "muc": "Hung", "trieu": "Nùng Vân Tế Nhật - Mưu sự bất thành",
        "slug": "thien-son-don",
    },
    {
        "so": 34, "ten": "Lôi Thiên Đại Tráng", "ten_ngan": "Đại Tráng", "han_tu": "大壯",
        "ngoai_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "noi_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "nhom_tuong": "Khôn", "ngu_hanh": "Thổ",
        "muc": "Cát", "trieu": "Công Sư Đắc Mộc - Vận khí sắp lên",
        "slug": "loi-thien-dai-trang",
    },
    {
        "so": 35, "ten": "Hỏa Địa Tấn", "ten_ngan": "Tấn", "han_tu": "晉",
        "ngoai_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "noi_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "nhom_tuong": "Càn", "ngu_hanh": "Kim",
        "muc": "Cát", "trieu": "Sừ Địa Đắc Kim - Vận đỏ sắp đến",
        "slug": "hoa-dia-tan",
    },
    {
        "so": 36, "ten": "Địa Hỏa Minh Di", "ten_ngan": "Minh Di", "han_tu": "明夷",
        "ngoai_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "noi_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "nhom_tuong": "Khảm", "ngu_hanh": "Thủy",
        "muc": "Hung", "trieu": "Quá Giang Chiết Kiều - Vô cùng khó khăn",
        "slug": "dia-hoa-minh-di",
    },
    {
        "so": 37, "ten": "Phong Hỏa Gia Nhân", "ten_ngan": "Gia Nhân", "han_tu": "家人",
        "ngoai_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "noi_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "nhom_tuong": "Tốn", "ngu_hanh": "Mộc",
        "muc": "Cát", "trieu": "Cảnh Lý Quan Hoa - Theo đuổi ảo ảnh",
        "slug": "phong-hoa-gia-nhan",
    },
    {
        "so": 38, "ten": "Hỏa Trạch Khuê", "ten_ngan": "Khuê", "han_tu": "睽",
        "ngoai_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "noi_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "nhom_tuong": "Cấn", "ngu_hanh": "Thổ",
        "muc": "Hung", "trieu": "Phản Mại Trư Dương - Long đong lận đận",
        "slug": "hoa-trach-khue",
    },
    {
        "so": 39, "ten": "Thủy Sơn Kiển", "ten_ngan": "Kiển", "han_tu": "蹇",
        "ngoai_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "noi_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "nhom_tuong": "Đoài", "ngu_hanh": "Kim",
        "muc": "Hung", "trieu": "Vũ Tuyết Tải Đồ - Mưu sự không đúng",
        "slug": "thuy-son-kien",
    },
    {
        "so": 40, "ten": "Lôi Thủy Giải", "ten_ngan": "Giải", "han_tu": "解",
        "ngoai_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "noi_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "nhom_tuong": "Chấn", "ngu_hanh": "Mộc",
        "muc": "Cát", "trieu": "Ngũ Quan Thoát Nạn - May mắn thoát nạn",
        "slug": "loi-thuy-giai",
    },
    {
        "so": 41, "ten": "Sơn Trạch Tổn", "ten_ngan": "Tổn", "han_tu": "損",
        "ngoai_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "noi_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "nhom_tuong": "Cấn", "ngu_hanh": "Thổ",
        "muc": "Bình Hòa", "trieu": "Thôi Xa Phí Lực - Uổng phí công sức",
        "slug": "son-trach-ton",
    },
    {
        "so": 42, "ten": "Phong Lôi Ích", "ten_ngan": "Ích", "han_tu": "益",
        "ngoai_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "noi_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "nhom_tuong": "Tốn", "ngu_hanh": "Mộc",
        "muc": "Cát", "trieu": "Khô Mộc Khai Hoa - Bĩ cực vinh lai",
        "slug": "phong-loi-ich",
    },
    {
        "so": 43, "ten": "Trạch Thiên Quải", "ten_ngan": "Quải", "han_tu": "夬",
        "ngoai_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "noi_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "nhom_tuong": "Khôn", "ngu_hanh": "Thổ",
        "muc": "Hung", "trieu": "Du Phong Thoát Võng - Gặp hung hóa cát",
        "slug": "trach-thien-quai",
    },
    {
        "so": 44, "ten": "Thiên Phong Cấu", "ten_ngan": "Cấu", "han_tu": "姤",
        "ngoai_quai": "☰ Càn (乾) - Thiên (天) tức Trời",
        "noi_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "nhom_tuong": "Càn", "ngu_hanh": "Kim",
        "muc": "Bình Hòa", "trieu": "Tha Hương Ngộ Hữu - Thời vận đã đến",
        "slug": "thien-phong-cau",
    },
    {
        "so": 45, "ten": "Trạch Địa Tụy", "ten_ngan": "Tụy", "han_tu": "萃",
        "ngoai_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "noi_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "nhom_tuong": "Đoài", "ngu_hanh": "Kim",
        "muc": "Cát", "trieu": "Ngư Lý Hóa Long - Rồng bay lên trời",
        "slug": "trach-dia-tuy",
    },
    {
        "so": 46, "ten": "Địa Phong Thăng", "ten_ngan": "Thăng", "han_tu": "升",
        "ngoai_quai": "☷ Khôn (坤) - Địa (地) tức Đất",
        "noi_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "nhom_tuong": "Chấn", "ngu_hanh": "Mộc",
        "muc": "Cát", "trieu": "Chỉ Nhật Cao Thăng - Phát tài phát lộc",
        "slug": "dia-phong-thang",
    },
    {
        "so": 47, "ten": "Trạch Thủy Khốn", "ten_ngan": "Khốn", "han_tu": "困",
        "ngoai_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "noi_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "nhom_tuong": "Đoài", "ngu_hanh": "Kim",
        "muc": "Bình Hòa", "trieu": "Thoát Lãng Trừu Đê - Tình trạng bất ổn",
        "slug": "trach-thuy-khon",
    },
    {
        "so": 48, "ten": "Thủy Phong Tỉnh", "ten_ngan": "Tỉnh", "han_tu": "井",
        "ngoai_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "noi_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "nhom_tuong": "Chấn", "ngu_hanh": "Mộc",
        "muc": "Bình Hòa", "trieu": "Khô Tỉnh Sanh Tuyền - Vận tốt đã đến",
        "slug": "thuy-phong-tinh",
    },
    {
        "so": 49, "ten": "Trạch Hỏa Cách", "ten_ngan": "Cách", "han_tu": "革",
        "ngoai_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "noi_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "nhom_tuong": "Khảm", "ngu_hanh": "Thủy",
        "muc": "Cát", "trieu": "Hạn Miêu Đắc Vũ - Vận tốt đã đến",
        "slug": "trach-hoa-cach",
    },
    {
        "so": 50, "ten": "Hỏa Phong Đỉnh", "ten_ngan": "Đỉnh", "han_tu": "鼎",
        "ngoai_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "noi_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "nhom_tuong": "Ly", "ngu_hanh": "Hỏa",
        "muc": "Cát", "trieu": "Ngư Ông Đắc Lợi - Nhất cử lưỡng tiện",
        "slug": "hoa-phong-dinh",
    },
    {
        "so": 51, "ten": "Lôi Vi Chấn", "ten_ngan": "Chấn", "han_tu": "震",
        "ngoai_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "noi_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "nhom_tuong": "Chấn", "ngu_hanh": "Mộc",
        "muc": "Bình Hòa", "trieu": "Kim Chung Dạ Tràng - Mọi sự thành công",
        "slug": "loi-vi-chan",
    },
    {
        "so": 52, "ten": "Sơn Vi Cấn", "ten_ngan": "Cấn", "han_tu": "艮",
        "ngoai_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "noi_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "nhom_tuong": "Cấn", "ngu_hanh": "Thổ",
        "muc": "Bình Hòa", "trieu": "Nhân Đoản Tháo Cao - Mọi việc bất thuận",
        "slug": "son-vi-can",
    },
    {
        "so": 53, "ten": "Phong Sơn Tiệm", "ten_ngan": "Tiệm", "han_tu": "漸",
        "ngoai_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "noi_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "nhom_tuong": "Cấn", "ngu_hanh": "Thổ",
        "muc": "Cát", "trieu": "Tuấn Mã Xuất Lung - Trứng để đầu đẳng",
        "slug": "phong-son-tiem",
    },
    {
        "so": 54, "ten": "Lôi Trạch Quy Muội", "ten_ngan": "Quy Muội", "han_tu": "歸妹",
        "ngoai_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "noi_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "nhom_tuong": "Đoài", "ngu_hanh": "Kim",
        "muc": "Hung", "trieu": "Duyên Mộc Cầu Ngư - Mưu sự bất thành",
        "slug": "loi-trach-quy-muoi",
    },
    {
        "so": 55, "ten": "Lôi Hỏa Phong", "ten_ngan": "Phong", "han_tu": "豐",
        "ngoai_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "noi_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "nhom_tuong": "Khảm", "ngu_hanh": "Thủy",
        "muc": "Cát", "trieu": "Cổ Kính Trùng Minh - Vận tốt trở lại",
        "slug": "loi-hoa-phong",
    },
    {
        "so": 56, "ten": "Hỏa Sơn Lữ", "ten_ngan": "Lữ", "han_tu": "旅",
        "ngoai_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "noi_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "nhom_tuong": "Ly", "ngu_hanh": "Hỏa",
        "muc": "Bình Hòa", "trieu": "Túc Điểu Phần Sào - Việc làm không thành",
        "slug": "hoa-son-lu",
    },
    {
        "so": 57, "ten": "Phong Vi Tốn", "ten_ngan": "Tốn", "han_tu": "巽",
        "ngoai_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "noi_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "nhom_tuong": "Tốn", "ngu_hanh": "Mộc",
        "muc": "Bình Hòa", "trieu": "Châu Đắc Thuận Phong - Khốn cực sinh phúc",
        "slug": "phong-vi-ton",
    },
    {
        "so": 58, "ten": "Trạch Vi Đoài", "ten_ngan": "Đoài", "han_tu": "兌",
        "ngoai_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "noi_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "nhom_tuong": "Đoài", "ngu_hanh": "Kim",
        "muc": "Cát", "trieu": "Chẩn Thủy Hòa Nê - Vô cùng thuận tiện",
        "slug": "trach-vi-doai",
    },
    {
        "so": 59, "ten": "Phong Thủy Hoán", "ten_ngan": "Hoán", "han_tu": "渙",
        "ngoai_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "noi_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "nhom_tuong": "Ly", "ngu_hanh": "Hỏa",
        "muc": "Hung", "trieu": "Cách Hà Vọng Kim - Uổng công phí sức",
        "slug": "phong-thuy-hoan",
    },
    {
        "so": 60, "ten": "Thủy Trạch Tiết", "ten_ngan": "Tiết", "han_tu": "節",
        "ngoai_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "noi_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "nhom_tuong": "Khảm", "ngu_hanh": "Thủy",
        "muc": "Cát", "trieu": "Trảm Tướng Phong Thần - Không phải kiêng kị",
        "slug": "thuy-trach-tiet",
    },
    {
        "so": 61, "ten": "Phong Trạch Trung Phu", "ten_ngan": "Trung Phu", "han_tu": "中孚",
        "ngoai_quai": "☴ Tốn (巽) - Phong (風) tức Gió",
        "noi_quai": "☱ Đoài (兌) - Trạch (澤) tức Đầm",
        "nhom_tuong": "Cấn", "ngu_hanh": "Thổ",
        "muc": "Cát", "trieu": "Hành Tẩu Bạc Băng - Vô cùng tốt lành",
        "slug": "phong-trach-trung-phu",
    },
    {
        "so": 62, "ten": "Lôi Sơn Tiểu Quá", "ten_ngan": "Tiểu Quá", "han_tu": "小過",
        "ngoai_quai": "☳ Chấn (震) - Lôi (雷) tức Sấm",
        "noi_quai": "☶ Cấn (艮) - Sơn (山) tức Núi",
        "nhom_tuong": "Đoài", "ngu_hanh": "Kim",
        "muc": "Bình Hòa", "trieu": "Cấp Quá Độc Kiều - Tiến lợi lui hại",
        "slug": "loi-son-tieu-qua",
    },
    {
        "so": 63, "ten": "Thủy Hỏa Ký Tế", "ten_ngan": "Ký Tế", "han_tu": "既濟",
        "ngoai_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "noi_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "nhom_tuong": "Khảm", "ngu_hanh": "Thủy",
        "muc": "Đại Cát", "trieu": "Kim Bảng Đề Danh - Cát khánh như ý",
        "slug": "thuy-hoa-ky-te",
    },
    {
        "so": 64, "ten": "Hỏa Thủy Vị Tế", "ten_ngan": "Vị Tế", "han_tu": "未濟",
        "ngoai_quai": "☲ Ly (離) - Hỏa (火) tức Hỏa",
        "noi_quai": "☵ Khảm (坎) - Thủy (水) tức Nước",
        "nhom_tuong": "Ly", "ngu_hanh": "Hỏa",
        "muc": "Hung", "trieu": "Thái Tuế Nguyệt Kiến - Tiểu nhân ám hại",
        "slug": "hoa-thuy-vi-te",
    },
]

# Map ngũ hành → emoji
NGU_HANH_EMOJI = {
    "Kim": "🥇", "Mộc": "🌳", "Thủy": "💧", "Hỏa": "🔥", "Thổ": "🏔️",
}

# Map mức cát/hung → emoji
MUC_EMOJI = {
    "Đại Cát": "🟢🟢", "Cát": "🟢", "Cát Hanh": "🟢✨",
    "Bình Hòa": "🟡", "Hung": "🔴",
}


class KinhDichService:
    """Xử lý rút quẻ Kinh Dịch và luận giải bằng Gemini API."""

    DETAIL_URL = "https://dich.kabala.vn/kinh-dich/{slug}"

    def __init__(self):
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self.model = Config.MODEL_NAME
        self.http_client = httpx.Client(timeout=10, follow_redirects=True)

    def fetch_detail(self, slug: str) -> str:
        """Fetch trang chi tiết quẻ từ kabala.vn, trích xuất nội dung quan trọng."""
        url = self.DETAIL_URL.format(slug=slug)
        try:
            resp = self.http_client.get(url)
            resp.raise_for_status()
            html = resp.text

            # Loại bỏ tất cả HTML tags, giữ text
            text = re.sub(r'<[^>]+>', '\n', html)
            # Loại bỏ nhiều dòng trống liên tiếp
            text = re.sub(r'\n{3,}', '\n\n', text)
            # Loại bỏ khoảng trắng thừa
            text = re.sub(r'[ \t]+', ' ', text)

            # Trích phần nội dung chính (từ "Tổng quan" đến "Danh sách 64 quẻ")
            start_marker = "Tổng quan quẻ"
            end_marker = "Danh sách 64 quẻ dịch"
            start_idx = text.find(start_marker)
            end_idx = text.find(end_marker)

            if start_idx != -1 and end_idx != -1:
                content = text[start_idx:end_idx].strip()
            elif start_idx != -1:
                content = text[start_idx:start_idx + 5000].strip()
            else:
                content = ""

            # Giới hạn độ dài để không vượt context window
            if len(content) > 4000:
                content = content[:4000] + "..."

            return content
        except Exception as e:
            log.warning(f"[kinhdich] Không thể fetch chi tiết quẻ {slug}: {e}")
            return ""

    def draw_hexagram(self, question: str) -> dict:
        """Random 1 trong 64 quẻ, dùng seed từ câu hỏi + timestamp."""
        current_time = str(time.time())
        seed_str = f"{question}_{current_time}"
        seed_int = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest(), 16)

        rng = random.Random(seed_int)
        hexagram = rng.choice(HEXAGRAMS)

        return hexagram

    def format_hexagram_text(self, h: dict) -> str:
        """Render thông tin quẻ dưới dạng text đẹp cho Discord."""
        muc_icon = MUC_EMOJI.get(h["muc"], "")
        hanh_icon = NGU_HANH_EMOJI.get(h["ngu_hanh"], "")

        return (
            f"## ☰ Quẻ {h['so']} · **{h['ten']}** ({h['han_tu']})\n"
            f"> *「{h['trieu']}」*\n\n"
            f"{muc_icon} {h['muc']}  ꞏ  {hanh_icon} {h['ngu_hanh']}  ꞏ  {h['nhom_tuong']}\n"
            f"┌  {h['ngoai_quai']}\n"
            f"└  {h['noi_quai']}\n"
        )

    def generate_reading(self, question: str, hexagram: dict, user_name: str) -> str:
        """Gọi Gemini để luận giải quẻ dịch dựa trên câu hỏi."""
        h = hexagram

        # Fetch thông tin chi tiết từ kabala.vn
        slug = h.get("slug", "")
        detail_text = self.fetch_detail(slug) if slug else ""

        detail_section = ""
        if detail_text:
            detail_section = (
                f"\n=== THÔNG TIN CHI TIẾT TỪ KINH DỊCH CỔ ĐIỂN ===\n"
                f"{detail_text}\n"
                f"=== HẾT THÔNG TIN CHI TIẾT ===\n\n"
            )

        prompt = (
            f"Bạn là một bậc thầy Kinh Dịch uyên bác, am hiểu sâu sắc triết học Đông phương, "
            f"64 quẻ dịch, bát quái, ngũ hành và lý thuyết âm dương.\n\n"

            f"Người dùng '{user_name}' hỏi: \"{question}\"\n\n"

            f"Quẻ đã rút:\n"
            f"- Quẻ số: {h['so']}\n"
            f"- Tên quẻ: {h['ten']} ({h['ten_ngan']} - {h['han_tu']})\n"
            f"- Ngoại quái: {h['ngoai_quai']}\n"
            f"- Nội quái: {h['noi_quai']}\n"
            f"- Nhóm tượng: {h['nhom_tuong']}\n"
            f"- Ngũ hành: {h['ngu_hanh']}\n"
            f"- Mức: {h['muc']}\n"
            f"- Triệu: {h['trieu']}\n"
            f"{detail_section}"

            f"Hãy luận giải theo các nguyên tắc sau:\n"
            f"- Sử dụng Thoán từ, Tượng quẻ, ý nghĩa chiêm bốc, tích xưa và lời đoán quẻ (nếu có) để luận giải sâu sắc.\n"
            f"- Giải thích ý nghĩa cốt lõi dựa trên tượng quái (ngoại quái + nội quái), "
            f"ngũ hành tương sinh/tương khắc, và triệu quẻ.\n"
            f"- Liên hệ trực tiếp với câu hỏi cụ thể của người dùng.\n"
            f"- Nêu cả mặt tích cực và thách thức.\n"
            f"- Văn phong trang trọng, sâu sắc nhưng dễ hiểu.\n"
            f"- Không mê tín tuyệt đối, trình bày như góc nhìn tham khảo.\n\n"

            f"Trả lời cực kỳ ngắn gọn theo đúng định dạng sau:\n\n"

            f"**Tổng quan:**\n"
            f"(1-2 câu tóm tắt ý nghĩa quẻ và kết luận chính)\n\n"

            f"**Phân tích quẻ:**\n"
            f"(Giải thích tượng quái, thoán từ, mối quan hệ ngoại/nội quái, ngũ hành, "
            f"và cách nó áp dụng vào tình huống của người hỏi)\n\n"

            f"**Lời khuyên:**\n"
            f"(1-2 câu ngắn gọn, thực tế, có thể hành động được)\n\n"

            f"Yêu cầu đặc biệt: Trả lời hoàn toàn bằng tiếng Việt."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            result = response.text.strip() if response.text else ""
            return result or "Quẻ dịch đang ẩn mình, xin hãy thử lại sau..."
        except Exception as e:
            log.error(f"[kinhdich] Lỗi khi gọi Gemini: {e}", exc_info=True)
            return "Đã có lỗi xảy ra khi luận giải quẻ dịch (Lỗi AI). Xin hãy thử lại sau."

    def generate_choice_reading(self, question_and_choices: str, hexagram: dict, user_name: str) -> str:
        """Gọi Gemini để quyết định một lựa chọn duy nhất dựa trên quẻ dịch."""
        h = hexagram

        # Fetch thông tin chi tiết từ kabala.vn
        slug = h.get("slug", "")
        detail_text = self.fetch_detail(slug) if slug else ""

        detail_section = ""
        if detail_text:
            detail_section = (
                f"\n=== THÔNG TIN CHI TIẾT TỪ KINH DỊCH CỔ ĐIỂN ===\n"
                f"{detail_text}\n"
                f"=== HẾT THÔNG TIN CHI TIẾT ===\n\n"
            )

        prompt = (
            f"Bạn là một bậc thầy Kinh Dịch uyên bác. "
            f"Người dùng '{user_name}' đang phân vân và đưa ra câu hỏi cùng các lựa chọn sau: \"{question_and_choices}\"\n\n"

            f"Quẻ đã rút:\n"
            f"- Quẻ số: {h['so']} - {h['ten']} ({h['ten_ngan']} - {h['han_tu']})\n"
            f"- Tượng quẻ: {h['ngoai_quai']} / {h['noi_quai']}\n"
            f"- Ngũ hành: {h['ngu_hanh']}, Mức: {h['muc']}\n"
            f"- Triệu: {h['trieu']}\n"
            f"{detail_section}"

            f"Dựa vào triết lý của quẻ dịch này, ngũ hành tương sinh/tương khắc và tình huống của người dùng, "
            f"bạn BẮT BUỘC PHẢI CHỌN ĐÚNG MỘT (1) lựa chọn tốt nhất trong số các lựa chọn mà người dùng đưa ra.\n\n"

            f"Trả lời cực kỳ ngắn gọn theo đúng định dạng sau:\n\n"

            f"**Lựa chọn:**\n"
            f"(Chỉ ghi rõ ràng MỘT lựa chọn mà bạn quyết định chọn)\n\n"

            f"**Lý giải từ quẻ dịch:**\n"
            f"(Giải thích tại sao lựa chọn đó là phù hợp nhất, dựa vào ý nghĩa của quẻ {h['ten']} và hoàn cảnh của người hỏi)\n\n"

            f"Yêu cầu đặc biệt: Trả lời hoàn toàn bằng tiếng Việt, tuyệt đối không được nói nước đôi hay né tránh việc chọn."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            result = response.text.strip() if response.text else ""
            return result or "Quẻ dịch đang ẩn mình, xin hãy thử lại sau..."
        except Exception as e:
            log.error(f"[kinhdich] Lỗi khi gọi Gemini: {e}", exc_info=True)
            return "Đã có lỗi xảy ra khi luận giải quẻ dịch (Lỗi AI). Xin hãy thử lại sau."

    def generate_thongke(self, user_name: str, history_texts: list[str]) -> str:
        """Gọi Gemini để tổng hợp và luận giải các lần gieo quẻ trong ngày của user."""
        
        prompt = (
            f"Bạn là một bậc thầy Kinh Dịch. Dưới đây là lịch sử gieo quẻ/vận may hôm nay của '{user_name}':\n"
            f"{chr(10).join(history_texts)}\n\n"
            f"Nhiệm vụ: Thống kê và luận giải vận trình theo ĐÚNG FORMAT CỐ ĐỊNH dưới đây.\n"
            f"Yêu cầu: CỰC KỲ NGẮN GỌN (mỗi mục 1-2 câu), đủ ý, KHÔNG dông dài, khoảng cách giữa các dòng nhỏ, dùng emoji.\n\n"
            f"**Thống kê nhanh:** (gạch dòng siêu ngắn: quẻ gì, tier gì, hỏi gì)\n"
            f"**🔮 Luận giải tổng quan:** \"[1 câu chốt]\" - [1-2 câu giải thích]\n"
            f"**💼 Công việc & Dự án:** [1 câu]\n"
            f"**❤️ Tình cảm & Nhân duyên:** [1 câu]\n"
            f"**🧘 Nội tâm:** [1 câu]\n"
            f"**🍀 Vận may:** [1 câu]\n\n"
            f"**💡 Lời khuyên cốt lõi:**\n"
            f"*[1 câu châm ngôn Kinh Dịch]*\n"
            f"✅ **Hãy làm:** [1 câu]\n"
            f"❌ **Hãy bỏ:** [1 câu]\n\n"
            f"Tuyệt đối tuân thủ cấu trúc này, không tự bịa thêm tiêu đề, trả lời bằng tiếng Việt."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            result = response.text.strip() if response.text else ""
            return result or "Các tinh tú đang che mờ thiên cơ, xin hãy thử lại sau..."
        except Exception as e:
            log.error(f"[kinhdich] Lỗi khi gọi Gemini: {e}", exc_info=True)
            return "Đã có lỗi xảy ra khi thống kê (Lỗi AI). Xin hãy thử lại sau."
