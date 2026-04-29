import chardet
import os
import re
import xml.etree.ElementTree as ET
import fitz

NS = '{http://www.gribuser.ru/xml/fictionbook/2.0}' # FB2_XML_NAMESPACE

def _format_metadata(pairs, fallback=""):
    """Format key-value pairs into metadata string."""
    formatted = [f"{key}: {value}" for key, value in pairs if value]
    return '\n'.join(formatted) if formatted else fallback

class Book:
    def __init__(self, filename):
        self.metadata = ""
        self.chapters = []
        self.filename = filename

    def parse(self):
        fn = self.filename

        with open(fn, "rb") as f:
            raw = f.read()

        file_extension = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ""

        if file_extension == "fb2":
            self._parse_fb2(raw)
        elif file_extension in ("epub", "pdf", "mobi", "cbz"):
            self._parse_with_mupdf(fn)
        else:
            self._parse_flat(raw)

    def _parse_fb2(self, raw_bytes):
        root = ET.fromstring(raw_bytes)

        desc = root.find(f'{NS}description')
        if desc is not None:
            pairs = []
            for el in desc.iter():
                if list(el):
                    continue
                tag = el.tag.replace(NS, '')
                text = ''.join(el.itertext()).strip()
                if text:
                    pairs.append((tag, text))
            self.metadata = _format_metadata(pairs)

        body = root.find(f'{NS}body')
        if body is None:
            return

        sections = body.findall(f'{NS}section')
        if not sections:
            return

        for section in sections:
            self.chapters.extend(self._extract_fb2_leaves(section))

    def _extract_fb2_leaves(self, section):
        nested = section.findall(f'{NS}section')
        if nested:
            leaves = []
            for sub in nested:
                leaves.extend(self._extract_fb2_leaves(sub))
            return leaves

        title_el = section.find(f'{NS}title')
        title = "".join(title_el.itertext()).strip() if title_el is not None else 'Untitled'

        paragraphs = []
        for p in section.findall(f'{NS}p'):
            text = "".join(p.itertext()).strip()
            if text:
                paragraphs.append(text)

        return [(title, "\n\n".join(paragraphs))]

    def _parse_with_mupdf(self, path):
        fitz.TOOLS.mupdf_display_errors(False)
        doc = fitz.open(path)
        try:
            metadata = doc.metadata
            pairs = list(metadata.items())
            self.metadata = _format_metadata(pairs, fallback=f"filename: {path}")

            toc = doc.get_toc()
            if not toc:
                raise ValueError("No TOC found")

            leaves = []
            for i, (level, title, page) in enumerate(toc):
                is_leaf = (i == len(toc) - 1) or (toc[i + 1][0] <= level)
                if is_leaf:
                    leaves.append((title, page))

            if not leaves:
                raise ValueError("No chapters found")

            for i, (title, start_page) in enumerate(leaves):
                end_page = leaves[i + 1][1] - 1 if i + 1 < len(leaves) else doc.page_count
                parts = []
                for page_index in range(start_page - 1, min(end_page, doc.page_count)):
                    blocks = doc[page_index].get_text("blocks")
                    for block in blocks:
                        if block[6] == 0 and block[4].strip():
                            parts.append(block[4].strip())
                text = '\n\n'.join(parts)
                if text:
                    self.chapters.append((title, text))
        finally:
            doc.close()

    def _parse_flat(self, raw_bytes):
        name = os.path.basename(self.filename)
        encoding = chardet.detect(raw_bytes)["encoding"] or "utf-8"
        text = raw_bytes.decode(encoding)

        chapter_pattern = re.compile(
            r'^[\x00-\x20]*(?:Глава|Chapter)?\s*(\d+|[IVXLCDM]+)[.:]?\s*(.*)$', 
            re.MULTILINE | re.IGNORECASE
        )
        matches = list(chapter_pattern.finditer(text))

        if matches:
            self.metadata = text[:matches[0].start()].strip()
            if not self.metadata:
                self.metadata = f"filename: {name}"

            for i, m in enumerate(matches):
                num = m.group(1).strip()
                rest = m.group(2).strip()
                title = f"{num} {rest}".strip()
                next_start = matches[i+1].start() if i + 1 < len(matches) else len(text)
                chapter_text = text[m.end():next_start].strip()
                if chapter_text:
                    self.chapters.append((title, chapter_text))
        else:
            self.metadata = f"filename: {name}"
            chunks = _split_text(text, desired=50000, max_limit=100000)
            for i, chunk in enumerate(chunks):
                self.chapters.append((f"Part {i + 1}", chunk))


def _split_text(text, desired, max_limit):
    """Split text into chunks respecting newline boundaries."""
    cuts = []
    for match in re.finditer(r'\n{2,}', text):
        weight = 2 if match.end() - match.start() >= 3 else 1
        cuts.append((match.end(), weight))
    cuts.sort()
    result, current_position = [], 0
    while current_position < len(text):
        if len(text) - current_position <= max_limit:
            chunk = text[current_position:].strip()
            if chunk:
                result.append(chunk)
            break
        valid = [(pos, weight) for pos, weight in cuts if current_position < pos <= current_position + max_limit]
        preferred = [(pos, weight) for pos, weight in valid if pos >= current_position + desired]

        if preferred:
            best = max(preferred, key=lambda x: x[1])
        elif valid:
            best = max(valid, key=lambda x: x[1])
        else:
            best = (current_position + max_limit, 0)
        chunk = text[current_position:best[0]].strip()
        if chunk:
            result.append(chunk)
        current_position = best[0]
    return result
