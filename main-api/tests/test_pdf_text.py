import pymupdf

from app.workers.pdf_text import extract_text

X = 50
# 10pt 글자의 줄 간격. WRAP은 줄바꿈으로 이어진 줄, NEXT는 다음 문단이다
WRAP = 12
NEXT = 24


def _pdf(tmp_path, pages):
    """pages: 쪽마다 (x, 기준선 y, 글, 글자 크기) 목록."""
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page()
        for x, y, text, size in lines:
            page.insert_text((x, y), text, fontname="korea", fontsize=size)
    path = tmp_path / "doc.pdf"
    doc.save(path)
    doc.close()
    return path


def _paragraphs(tmp_path, pages):
    return extract_text(_pdf(tmp_path, pages)).split("\n\n")


def test_wrapped_lines_are_joined_into_one_paragraph(tmp_path):
    y = 100
    paragraphs = _paragraphs(
        tmp_path,
        [[
            (X, y, "청크 문맥 유실 문제 해", 10),
            (X, y + WRAP, "결 방법을 정리했다.", 10),
            (X, y + WRAP + NEXT, "지연은 Prometheus와", 10),
            (X, y + 2 * WRAP + NEXT, "Grafana로 본다.", 10),
        ]],
    )
    # 한글 사이에서 바뀐 줄은 붙이고, 영문이 닿으면 띄운다
    assert paragraphs == ["청크 문맥 유실 문제 해결 방법을 정리했다.", "지연은 Prometheus와 Grafana로 본다."]


def test_lines_with_paragraph_spacing_stay_separate(tmp_path):
    paragraphs = _paragraphs(tmp_path, [[(X, 100, "첫 문장이다.", 10), (X, 100 + NEXT, "둘째 문장이다.", 10)]])
    assert paragraphs == ["첫 문장이다.", "둘째 문장이다."]


def test_heading_with_other_font_size_is_its_own_paragraph(tmp_path):
    paragraphs = _paragraphs(tmp_path, [[(X, 100, "1.1 배경", 11.5), (X, 100 + WRAP, "본문이다.", 10)]])
    assert paragraphs == ["1.1 배경", "본문이다."]


def test_bullet_items_are_separate_paragraphs_with_their_marker(tmp_path):
    y = 100
    paragraphs = _paragraphs(
        tmp_path,
        [[
            (X + 10, y, "•", 10), (X + 16, y, "Confluence를 색인한다.", 10),
            (X + 10, y + WRAP, "•", 10), (X + 16, y + WRAP, "슬랙 봇으로 답한다.", 10),
        ]],
    )
    # 글머리표와 본문 사이 띄어쓰기는 PDF마다 다르다
    assert [p.replace(" ", "") for p in paragraphs] == ["•Confluence를색인한다.", "•슬랙봇으로답한다."]


def test_repeated_header_and_page_number_are_removed(tmp_path):
    pages = [
        [
            (X, 30, "KnowBridge 프로젝트 문서 v1.2", 8),
            (X, 100, f"{n}쪽 본문이다.", 10),
            (280, 815, f"{n} / 3", 8.5),
        ]
        for n in (1, 2, 3)
    ]
    assert _paragraphs(tmp_path, pages) == ["1쪽 본문이다.", "2쪽 본문이다.", "3쪽 본문이다."]


def test_margin_text_on_too_few_pages_is_kept(tmp_path):
    pages = [[(X, 30, "제목", 8), (X, 100, "본문이다.", 10)], [(X, 30, "제목", 8), (X, 100, "끝.", 10)]]
    assert _paragraphs(tmp_path, pages) == ["제목", "본문이다.", "제목", "끝."]
