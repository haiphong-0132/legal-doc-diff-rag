import json
from pathlib import Path
from typing import List, Dict, Any

from tqdm import tqdm


def _load_chroma_snapshot(snapshot_path: str | Path) -> Dict[str, Any]:
    """
    Đọc file JSON snapshot của ChromaDB được tạo ra từ:
        chroma_store.collection.get(include=['documents', 'metadatas'])
    (xem file `debug_chroma_collection.json` trong project).
    """
    snapshot_path = Path(snapshot_path)
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Không tìm thấy snapshot ChromaDB: {snapshot_path}")

    with snapshot_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Kiểm tra cấu trúc tối thiểu
    if not isinstance(data, dict) or "ids" not in data or "documents" not in data or "metadatas" not in data:
        raise ValueError("File snapshot không đúng định dạng mong đợi (thiếu 'ids' / 'documents' / 'metadatas').")

    return data


def _normalize_text(text: str) -> str:
    """
    Chuẩn hóa text để gần giống khi hiển thị trong Word:
    - Chuyển các ký tự xuống dòng dạng '\r.' trong snapshot về newline thật.
    - Chuẩn hóa về '\n'.
    - Bỏ dòng 'Mã đoạn: ...', chỉ giữ các dòng tiêu đề + nội dung.
    """
    if not isinstance(text, str):
        return str(text)

    # Trong debug_chroma_collection.json chuỗi thường có '\r.' đứng trước dấu xuống dòng
    cleaned = text.replace("\r.\n", "\n").replace("\r.", "\n").replace("\r\n", "\n").replace("\r", "\n")

    lines = cleaned.split("\n")

    # Bỏ dòng "Mã đoạn: ..."
    if lines and lines[0].strip().startswith("Mã đoạn:"):
        lines = lines[1:]

    processed: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        # Bỏ prefix "Tiêu đề:" và "Nội dung:" nhưng giữ lại nội dung phía sau
        if stripped.startswith("Tiêu đề:"):
            new_line = stripped[len("Tiêu đề:") :].lstrip()
        elif stripped.startswith("Nội dung:"):
            new_line = stripped[len("Nội dung:") :].lstrip()
        else:
            new_line = line
        processed.append(new_line)

    # Xóa các dòng trống đầu/cuối dư thừa
    while processed and not processed[0].strip():
        processed.pop(0)
    while processed and not processed[-1].strip():
        processed.pop()

    return "\n".join(processed)


def collect_section_contents(
    chroma_data: Dict[str, Any],
    section_id: str,
) -> List[str]:
    """
    Lấy nội dung của 1 section_id và toàn bộ các phần tử con của nó.

    Logic:
    - Mỗi phần tử trong ChromaDB có:
        ids[i]        ~ section_id (vd: 'dieu_3.khoan_3_1.diem_3_1_1')
        documents[i]  ~ nội dung text tương ứng
        metadatas[i]  ~ chứa 'section_id' giống với ids[i]
    - Phần tử con được xác định bằng tiền tố: bắt đầu bằng 'section_id.'
      Ví dụ: section_id='dieu_3' => lấy thêm:
          'dieu_3.khoan_3_1', 'dieu_3.khoan_3_1.diem_3_1_1', ...
    """
    ids: List[str] = chroma_data.get("ids", [])
    documents: List[str] = chroma_data.get("documents", [])
    metadatas: List[Dict[str, Any]] = chroma_data.get("metadatas", [])

    if not (len(ids) == len(documents) == len(metadatas)):
        raise ValueError("Độ dài ids / documents / metadatas không khớp trong snapshot ChromaDB.")

    target_prefix = f"{section_id}."
    collected_texts: List[str] = []

    for idx, sec_id in enumerate(ids):
        if sec_id == section_id or sec_id.startswith(target_prefix):
            collected_texts.append(_normalize_text(documents[idx]))

    return collected_texts


def write_to_markdown(texts: List[str], output_path: str | Path) -> None:
    """
    Ghi danh sách đoạn text ra file markdown.
    Mỗi đoạn được ngăn cách bởi 1 dòng trống để dễ đọc.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = "\n\n".join(texts)

    with output_path.open("w", encoding="utf-8") as f:
        f.write(content)


def retrieve_section_to_file(
    section_id: str,
    snapshot_path: str | Path = "debug_chroma_collection.json",
    output_path: str | Path = "retrieval_output.md",
) -> None:
    """
    API chính:
    - Đọc dữ liệu snapshot Chroma từ `snapshot_path`
    - Tìm nội dung của `section_id` và các phần tử con
    - Ghi kết quả ra `output_path` theo đúng thứ tự xuất hiện trong Chroma.
    """
    tqdm.write(f"Đang đọc snapshot Chroma từ: {snapshot_path}")
    chroma_data = _load_chroma_snapshot(snapshot_path)

    tqdm.write(f"Đang lấy nội dung cho section_id: {section_id}")
    texts = collect_section_contents(chroma_data, section_id)

    if not texts:
        tqdm.write(f"Không tìm thấy section_id hoặc phần tử con cho: {section_id}")
        return

    tqdm.write(f"Tìm thấy {len(texts)} đoạn, đang ghi ra file: {output_path}")
    write_to_markdown(texts, output_path)
    tqdm.write("Hoàn thành ghi kết quả.")


def main() -> int:
    """
    Chương trình chạy từ terminal:
    - Hỏi người dùng nhập section_id
    - Đọc 'debug_chroma_collection.json' ở thư mục project root
    - Ghi kết quả ra 'retrieval_output.md'
    """
    try:
        section_id = input("Nhập section_id cần truy xuất (ví dụ: dieu_3, dieu_3.khoan_3_1, ...): ").strip()
        if not section_id:
            print("section_id không được để trống.")
            return 1

        project_root = Path(__file__).resolve().parents[3]
        snapshot_path = project_root / "debug_chroma_collection.json"
        output_path = project_root / "src" / "core" / "retrieval" / "retrieval_output.md"

        retrieve_section_to_file(
            section_id=section_id,
            snapshot_path=snapshot_path,
            output_path=output_path,
        )
        return 0
    except KeyboardInterrupt:
        print("\nĐã hủy bởi người dùng.")
        return 1
    except Exception as e:
        print(f"Lỗi khi truy xuất section: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

