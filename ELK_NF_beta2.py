from openai import OpenAI
import xml.etree.ElementTree as ET
import re
import sys
import time

# Электронный Литературный Критик Научной Фантастики (ЭЛК/НФ Бета 2)
# Разбивает произведение на части по нескольку глав и оценивает его по набору критериев.
# В конце работы выводит итоговую оценку.
# Недетерминистичен, подвержен легким перепадам настроения, не заменяет ваше собственное мнение.
# В данный момент настроен на использование локальной Qwen 3.6 27B в не думающем режиме (Контекст 80k).
# Примечание: можно свободно менять критерии оценки произведения по своему вкусу.

SYSTEM_PROMPT_ANALYZE = '''Ты литературовед, специализирующийся на научной фантастике. Анализируй текст последовательно и объективно.'''

USER_PROMPT_ANALYZE = '''Анализируй этот фрагмент текста научной фантастики.
Выводи результат строго в Markdown с заголовками:

### Сюжет
(Кратко: кто, что, куда, ключевые повороты)

### Научные и технологические концепции
(Выдели конкретные идеи, оцени их правдоподобность и роль в сюжете)

### Персонажи
(Мотивы, развитие, уникальность)

### Философские и моральные аспекты
(Какие вопросы поднимает автор?)

### Стиль и проза
(Язык, ритм, атмосфера)

Текст для анализа:
<text>
{TEXT}
</text>'''

SYSTEM_PROMPT_SYNTHESIS = '''Ты строгий литературный критик научной фантастики в стиле Айзека Азимова и Урсулы Ле Гуин. Твой анализ глубок, точен и не терпит компромиссов.'''

USER_PROMPT_SYNTHESIS = '''На основе предоставленных фрагментов резюме проанализируй произведение и выстави ему оценки по критериям:

### Критерии хорошей научной фантастики
1. **Большая идея (Big Idea)** — есть ли оригинальная концепция?
2. **Баланс науки и художественности** — наука направляет сюжет или подчиняется ему?
3. **Исследование и достоверность** — элементы опираются на реальные знания?
4. **Персонажи** — живые и многомерные или марионетки?
5. **Философская и моральная глубина** — задаёт ли произведение сложные вопросы?
6. **Качество прозы** — текст течёт или борешься с ним?
7. **Консистентность мира** — внутренняя логика не нарушается?
8. **Эмоциональный вес** — вызывает ли произведение сильные чувства?
9. **Смелость и оригинальность** — автор рискует или следует шаблонам?
10. **Долговечность** — актуально ли это будет через десятилетия?
11. **Прогностическая ценность** — Произведение резонирует с современными технологическими, экологическими или социальными процессами, часто опережая общественную дискуссию.

---

### Критерии плохой научной фантастики и плохого произведения в целом

1. **Нарушение внутренней логики и сюжетные дыры**
   Противоречия в правилах мира, внезапные «спасительные технологии», решения проблем за счёт не заявленных ранее возможностей.
2. **Плоские персонажи и отсутствие развития**
   Герои клишированы, ведут себя неестественно, служат лишь иллюстрацией тезиса автора или двигателем сюжета без внутренней жизни.
3. **Вторичность и эксплуатация тропов без осмысления**
   Механическое повторение штампов без новаторства, иронии, деконструкции или глубины.
4. **Псевдонаучность или «магия под видом науки»**
   Технология работает «потому что так надо», без внутренней механики, ограничений или хотя бы честного признания условности. Нарушает контракт жанра.
5. **Поверхностность тем и назидательность**
   Упрощённые моральные уроки, отсутствие нюансов, идеологическая пропаганда вместо художественного диалога с читателем.
6. **Отсутствие смысловой и эмоциональной кульминации**
   Финал не вытекает из логики мира и характеров, оставляет чувство пустоты, недосказанности или искусственности.
7. **Игнорирование жанровых ожиданий без художественной цели**
   Нарушение правил НФ не ради эксперимента, переосмысления или метафоры, а из-за небрежности, непонимания жанра или спешки.
8. **Винегрет** Жанровая смесь без какой-либо цели, призванная лишь запутать читателя и добавить объёма произведению.

---

### Инструкция по оценке:
1. Для каждого позитивного критерия напиши 1-2 предложения обоснования и выставь балл по десятибальной шкале:
- 10/10 -> Безупречно, эталон жанра
- 9/10 -> Отлично, без заметных проблем
- 8/10 -> Очень хорошо, мелкие шероховатости
- 7/10 -> Хорошо, есть недостатки, но не критичные
- 6/10 -> Выше среднего, заметные проблемы
- 5/10 -> Средне, произведение держится на минимуме
- 4/10 -> Ниже среднего, проблемы существенны
- 3/10 -> Плохо, серьёзные недостатки
- 2/10 -> Очень плохо, критерий почти провален
- 1/10 -> Полностью провален

Пример:
Персонажи: 7/10 — Главный герой имеет ясную мотивацию и проходит дугу развития, но второстепенные персонажи одномерны.

2. Для каждого негативного критерия напиши 1-2 предложения обоснования и выставь балл по десятибальной шкале насколько существенен данный недостаток:
- 0/10 -> Недостаток не замечен.
- 1/10 -> Минимальный, скорее перешёл в достоинство.
- 2/10 -> Незначительный, не мешает восприятию.
- 3/10 -> Лёгкий недостаток, терпимо.
- 4/10 -> Качественно хуже, но терпимо.
- 5/10 -> Заметно портит впечатление.
- 6/10 -> Сильно мешает, но суть произведения ещё угадывается.
- 7/10 -> Больно читать, серьёзно урон качество.
- 8/10 -> Почти разрушает произведение.
- 9/10 -> Суть разрушена, читать крайне тяжело.
- 10/10 -> Полное разрушение, читать невозможно.

3. На данном этапе НЕ подсчитывай суммы очков.

Фрагменты анализа:
<summaries>
{SUMMARIES}
</summaries>'''

USER_PROMPT_CALCULATE = '''Ниже приведён текст твоего финального анализа произведения.
Извлеки из него числовые оценки и выведи их строго в формате XML.

Достоинства (11 критериев, чем выше — тем лучше):

<strengths>
  <score name="Большая идея">3</score>
  <score name="Баланс науки и художественности">5</score>
  <score name="Исследование и достоверность">7</score>
  <score name="Персонажи">8</score>
  <score name="Философская и моральная глубина">10</score>
  <score name="Качество прозы">2</score>
  <score name="Консистентность мира">4</score>
  <score name="Эмоциональный вес">6</score>
  <score name="Смелость и оригинальность">9</score>
  <score name="Долговечность">10</score>
  <score name="Прогностическая ценность">3</score>
</strengths>

Недостатки (8 критериев, чем выше — тем хуже):

<weaknesses>
  <score name="Нарушение внутренней логики и сюжетные дыры">0</score>
  <score name="Плоские персонажи и отсутствие развития">0</score>
  <score name="Вторичность и эксплуатация тропов">0</score>
  <score name="Псевдонаучность">0</score>
  <score name="Поверхностность тем и назидательность">0</score>
  <score name="Отсутствие кульминации">0</score>
  <score name="Игнорирование жанровых ожиданий">0</score>
  <score name="Винегрет">0</score>
</weaknesses>

Ничего кроме блоков <strengths>...</strengths> и <weaknesses>...</weaknesses> выводить не нужно.

Текст анализа:
<analysis>
{SYNTHESIS}
</analysis>'''

# ANSI color codes
COLORS = {
    'red': '\033[91m',
    'green': '\033[92m',
    'yellow': '\033[93m',
    'blue': '\033[94m',
    'magenta': '\033[95m',
    'cyan': '\033[96m',
    'white': '\033[97m',
    'gray': '\033[90m',
    'reset': '\033[0m'
}

def cprint(text, color='white', **kwargs):
    """Print colored text"""
    code = COLORS.get(color, COLORS['white'])
    print(f"{code}{text}{COLORS['reset']}", **kwargs)

class LLM:
    def __init__(self, url="http://localhost:8080/v1/chat/completions", api_key=""):
        self.client = OpenAI(base_url=url.replace("/v1/chat/completions", "/v1"), api_key=api_key)

    def call(self, prompt, system="You are a helpful assistant."):
        for attempt in range(5):
            try:
                stream = self.client.chat.completions.create(
                    model="current_model",
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=50000,
                    stream=True,
                    extra_body={
                        "temperature": 0.1,
                        "top_p" : 0.1,
                        "top_k": 20,
                        "min_p" : 0.0,
                        "presence_penalty": 0.0,
                        "repetition_penalty": 1.0,
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                )
                
                content = ""
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        cprint(delta.reasoning_content, 'gray', end="", flush=True)
                    if delta.content:
                        print(delta.content, end="", flush=True)
                        content += delta.content
                        
                if content and len(content) > 10:
                    return content
                cprint("  -> Warning: Empty response, retrying...", 'yellow')
            except Exception as e:
                cprint(f"  -> Error (attempt {attempt+1}): {e}", 'red')
            
            time.sleep(5 * (2 ** attempt))
        return "[Error: empty response]"

NS = '{http://www.gribuser.ru/xml/fictionbook/2.0}'

def get_meta(root):
    """Extract all description fields as key-value pairs."""
    desc = root.find(f'{NS}description')
    if desc is None:
        return ""
    pairs = []
    for el in desc.iter():
        if list(el): # skip parents to avoid duplicates
            continue
        tag = el.tag.replace(NS, '')
        text = ''.join(el.itertext()).strip()
        if text:
            pairs.append(f"{tag}: {text}")
    return '\n'.join(pairs)

def get_chapters(root):
    body = root.find(f'{NS}body')
    if body is None:
        raise ValueError("No body found in FB2")

    def get_text(el):
        """Extract full text including inline tags."""
        if el is None:
            return ""
        return "".join(el.itertext()).strip()

    # 1. Structured: recursive leaf extraction
    def extract_leaves(section):
        nested = section.findall(f'{NS}section')
        if nested:
            for sub in nested:
                yield from extract_leaves(sub)
        else:
            title_el = section.find(f'{NS}title')
            title = get_text(title_el) if title_el is not None else 'Untitled'
            
            text_parts = []
            # Only direct <p> children, excluding metadata containers
            for p in section.findall(f'{NS}p'):
                text = get_text(p)
                if text:
                    text_parts.append(text)
            yield title, "\n\n".join(text_parts)

    sections = body.findall(f'{NS}section')
    if sections:
        for sec in sections:
            yield from extract_leaves(sec)
        return

    # 2. Flat heuristics
    raise NotImplementedError("Flat heuristics")

def parse_scores_xml(text):
    """Extract <strengths> and <weaknesses> blocks from LLM output."""
    def parse_block(tag):
        match = re.search(f'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
        if not match:
            cprint(f"  -> Error: <{tag}> block not found", 'red')
            return None
        xml_block = f"<{tag}>{match.group(1)}</{tag}>"
        try:
            root = ET.fromstring(xml_block)
            return [(s.get('name', '?'), float(s.text.strip())) for s in root.findall('score')]
        except ET.ParseError as e:
            cprint(f"  -> Error: Malformed XML in <{tag}> — {e}", 'red')
            return None
        except Exception as e:
            cprint(f"  -> Error parsing <{tag}>: {e}", 'red')
            return None

    strengths = parse_block('strengths')
    weaknesses = parse_block('weaknesses')
    return strengths, weaknesses

def print_scores(title, scores, color):
    """Print scores with average."""
    if not scores:
        return
    avg = sum(v for _, v in scores) / len(scores)
    cprint(f"\n  {title} (avg: {avg:.2f})", color)
    for name, val in scores:
        cprint(f"    {name}: {val}", color)

def run(path):
    model = LLM()
    summaries = []
    
    acc_text = ""
    
    def analyze_chunk(text, chapters, meta=""):
        cprint(f"\n\nSending chunk ({len(text)} chars):\n{'\n'.join(chapters)}", 'magenta')
        if meta:
            text = f"[METADATA]\n{meta}\n\n{text}"
        prompt = USER_PROMPT_ANALYZE.replace("{TEXT}", text)
        response = model.call(prompt, system=SYSTEM_PROMPT_ANALYZE)
        summaries.append(response)
        return f"\n\n[ANALYSIS]\n{response}"

    CHUNK_FOR_LLM = 50*1024
    current_chapters = []
    
    fb2_root = ET.parse(path).getroot()

    meta = get_meta(fb2_root)
    if meta:
        cprint(f"[METADATA]\n{meta}", 'blue')
    
    for title, text in get_chapters(fb2_root):
        if not text.strip():
            continue
        
        if acc_text and len(acc_text) + len(text) > CHUNK_FOR_LLM:
            acc_text = analyze_chunk(acc_text, current_chapters, meta)
            current_chapters = []
            
        acc_text += f"\n\n[CHAPTER: {title}]\n{text}"
        current_chapters.append(title)
            
    if acc_text.strip():
        analyze_chunk(acc_text, current_chapters, meta)

    summaries_text = "\n\n---\n\n".join(summaries)
    if meta:
        summaries_text = f"[METADATA]\n{meta}\n\n{summaries_text}"
    final_prompt = USER_PROMPT_SYNTHESIS.replace("{SUMMARIES}", summaries_text)
    
    cprint("\n\nFINAL SYNTHESIS...", 'magenta')
    synthesis = model.call(final_prompt, system=SYSTEM_PROMPT_SYNTHESIS)

    cprint("\n\nCALCULATING SCORE...", 'magenta')
    calc_prompt = USER_PROMPT_CALCULATE.replace("{SYNTHESIS}", synthesis)
    calc_response = model.call(calc_prompt, system=SYSTEM_PROMPT_SYNTHESIS)
    strengths, weaknesses = parse_scores_xml(calc_response)

    avg_s = sum(v for _, v in strengths) / len(strengths)
    print(f"\n  ДОСТОИНСТВА (avg: {avg_s:.2f})")
    for name, val in strengths:
        print(f"    {name}: {val}")
    
    avg_w = sum(v for _, v in weaknesses) / len(weaknesses)
    print(f"\n  НЕДОСТАТКИ (avg: {avg_w:.2f})")
    for name, val in weaknesses:
        print(f"    {name}: {val}")

    cprint(f'{'='*40}')
    cprint(f'ОБЩАЯ ОЦЕНКА: {avg_s:.2f}/-{avg_w:.2f}', 'magenta')

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run(sys.argv[1])
    else:
        print(f"Usage: python {sys.argv[0]} <path_to_book.fb2>")
