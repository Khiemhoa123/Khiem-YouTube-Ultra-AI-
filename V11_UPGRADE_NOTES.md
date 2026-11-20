# Khiêm YouTube V11: cập nhật và kiểm thử

## Các thay đổi đã đưa lên nhánh mặc định
- AI SMART TIMELINE giữ mục tiêu và ngưỡng tối thiểu video, ưu tiên mức liên quan nội dung.
- Phối hợp lời Whisper với ngữ cảnh TXT khi chấm điểm ảnh và video.
- Cache tên file và sidecar TXT trong một lượt dựng timeline.
- Lựa chọn ngẫu nhiên có seed ổn định khi voice và cài đặt không đổi.
- Cache CLIP, Whisper và timeline vẫn được giữ.
- AUTO QUALITY CHECK kiểm tra đường dẫn media, thời lượng, tỉ lệ video trước khi xuất.
- Giao diện biên tập có cuộn chuột, các dòng cài đặt gọn hơn.
- SMART INTERVIEW INTRO giữ nguyên cơ chế chọn đoạn và fallback có sẵn.

## Cập nhật trên Windows
1. Thoát phần mềm và CapCut. Sao lưu thư mục phần mềm đang hoạt động.
2. Vào repository GitHub, chọn Code > Download ZIP.
3. Giải nén và chép toàn bộ file .py mới vào thư mục phần mềm hiện tại, ghi đè khi Windows hỏi. Không xóa models, template, dữ liệu, settings, cache hay thư mục media của bạn.
4. Mở CMD ngay trong thư mục phần mềm rồi chạy: python khiem_ui.py

## Kiểm thử tối thiểu trước khi dùng dự án thật
1. Dùng một dự án nhỏ có Voice MP3, TXT và media theo cùng số thứ tự.
2. Chạy Kiểm tra tư liệu, xem thông báo QA.
3. Xuất CapCut, mở lại CapCut và xác nhận clip, audio, intro ở đầu timeline.
4. Xuất MP4 và nghe thử đoạn đầu, đoạn chuyển giọng phỏng vấn sang Voice AI và đoạn cuối.
5. Thay một ảnh nguồn, chạy lại để kiểm tra cache được làm mới.
6. Nếu phát sinh lỗi, đóng phần mềm và khôi phục bản sao lưu.

Lưu ý: Các commit đã được ghi vào GitHub nhưng chưa được chạy thử trên Windows trong môi trường này. Tên V11 không đồng nghĩa đã xác nhận mọi tính năng hoạt động hoàn hảo.
