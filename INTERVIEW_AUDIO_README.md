# Tab 05 - Interview Audio

Tab này nhận một video phỏng vấn, nhận diện tối đa hai hoặc ba người nói, ghép các lượt nói của từng người theo thứ tự thời gian và xuất `Speaker_01.mp3`, `Speaker_02.mp3`, `Speaker_03.mp3` vào thư mục bạn chọn.

## Cài đặt một lần

Phần mềm cần FFmpeg và FFprobe có trong PATH, cùng các thư viện Python:

```powershell
python -m pip install torch torchaudio "pyannote.audio>=3.1,<4"
```

Mở https://huggingface.co/pyannote/speaker-diarization-3.1 và https://huggingface.co/pyannote/segmentation-3.0 để chấp nhận điều kiện sử dụng mô hình. Tạo Hugging Face access token có quyền đọc. Dán token vào Tab 05 khi chạy. Token không được ghi vào cấu hình phần mềm.

## Cách dùng

1. Bấm Update và khởi động lại Khiêm Youtube.
2. Mở **05 INTERVIEW AUDIO**, chọn video và thư mục xuất.
3. Nhập token, chọn **2** hoặc **3** người, thời lượng **30-40 giây**.
4. Bấm **TÁCH SPEAKER VÀ XUẤT MP3** và theo dõi nhật ký.

## Giới hạn

- Đây là **speaker diarization**, không phải mô hình tách tín hiệu khi hai giọng nói chồng nhau. Các đoạn chồng tiếng bị bỏ qua.
- Số speaker cần chọn đúng với số người có lời nói trong video. Nhãn Speaker 01/02/03 là theo thứ tự xuất hiện, không xác minh danh tính.
- Nếu một speaker có ít hơn 30 giây lời nói riêng biệt, sẽ không xuất file cho speaker đó.
- Việc nối nhiều lượt nói có thể làm nội dung nghe không liên tục. Hãy nghe lại trước khi sử dụng hoặc đăng tải, không trình bày bản ghép như một câu trả lời nguyên vẹn.
- Tốc độ lần đầu phụ thuộc việc tải model. Cần kết nối Internet và quyền truy cập mô hình.
