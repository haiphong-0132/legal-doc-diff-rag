const DICT = {
  modau: 'Mở đầu',
  chinh: 'Chính',
  dieu: 'Điều',
  khoan: 'Khoản',
  diem: 'Điểm',
};

/**
 * Chuyển section_id thành dạng dễ đọc.
 * Ví dụ: "dieu_2.khoan_2_2" → "Khoản 2.2 Điều 2"
 */
export function decodeChunkId(id) {
  if (!id) return 'Không rõ';
  try {
    const levels = id.trim().split('.');
    const decoded = levels.map((level) => {
      const sep = level.indexOf('_');
      if (sep === -1) return level;
      const le = level.slice(0, sep);
      const index = level.slice(sep + 1).split('_').join('.');
      return DICT[le] ? `${DICT[le]} ${index}` : level;
    });
    return decoded.reverse().join(', ');
  } catch {
    return id;
  }
}
