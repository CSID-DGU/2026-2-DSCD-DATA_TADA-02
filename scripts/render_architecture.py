"""Render editable SVG plus matching PNG engineering diagrams. No image generation."""
import html
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/diagrams"
INK, MUTED, TEAL, LINE = "#0a1f43", "#536a89", "#009da5", "#cbdce7"


class Diagram:
    def __init__(self, width, height, title, subtitle):
        self.width, self.height = width, height
        self.image = Image.new("RGB", (width, height), "#f3f9fc")
        self.draw = ImageDraw.Draw(self.image)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                    '<rect width="100%" height="100%" fill="#f3f9fc"/>']
        self.text(50, 30, title, 36, bold=True)
        self.text(50, 86, subtitle, 19, MUTED)

    def font(self, size, bold=False):
        return ImageFont.truetype(f"C:/Windows/Fonts/{'malgunbd' if bold else 'malgun'}.ttf", size)

    def text(self, x, y, value, size=20, color=INK, bold=False):
        self.draw.text((x, y), value, font=self.font(size, bold), fill=color)
        weight = "700" if bold else "400"
        self.svg.append(f'<text x="{x}" y="{y + size}" font-family="Malgun Gothic, sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}">{html.escape(value)}</text>')

    def box(self, x, y, width, height, title, lines, fill="white", stroke=LINE, dashed=False, title_size=24):
        self.draw.rounded_rectangle((x, y, x + width, y + height), radius=15, fill=fill, outline=stroke, width=2)
        dash = ' stroke-dasharray="8 6"' if dashed else ''
        self.svg.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="15" fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>')
        self.text(x + 22, y + 17, title, title_size, bold=True)
        for i, line in enumerate(lines):
            self.text(x + 22, y + 62 + i * 31, line, 19, MUTED)

    def arrow(self, points, label=None, label_at=None, dashed=False, color=TEAL):
        for start, end in zip(points, points[1:]):
            if dashed:
                distance = math.dist(start, end)
                for offset in range(0, int(distance), 16):
                    t1, t2 = offset / distance, min(offset + 9, distance) / distance
                    p1 = tuple(a + (b - a) * t1 for a, b in zip(start, end))
                    p2 = tuple(a + (b - a) * t2 for a, b in zip(start, end))
                    self.draw.line([p1, p2], fill=color, width=3)
            else:
                self.draw.line([start, end], fill=color, width=3)
        a, b = points[-2:]
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        triangle = [b, (b[0] - 13 * math.cos(angle - .45), b[1] - 13 * math.sin(angle - .45)),
                    (b[0] - 13 * math.cos(angle + .45), b[1] - 13 * math.sin(angle + .45))]
        self.draw.polygon(triangle, fill=color)
        dash = ' stroke-dasharray="9 7"' if dashed else ''
        coords = " ".join(f"{x},{y}" for x, y in points)
        self.svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3"{dash}/>')
        self.svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x, y in triangle)}" fill="{color}"/>')
        if label and label_at:
            x, y = label_at
            bbox = self.draw.textbbox((x, y), label, font=self.font(16))
            self.draw.rectangle((bbox[0] - 5, bbox[1] - 3, bbox[2] + 5, bbox[3] + 3), fill="#f3f9fc")
            self.svg.append(f'<rect x="{bbox[0]-5}" y="{bbox[1]-3}" width="{bbox[2]-bbox[0]+10}" height="{bbox[3]-bbox[1]+6}" fill="#f3f9fc"/>')
            self.text(x, y, label, 16, color)

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        self.image.save(OUT / f"{name}.png")
        (OUT / f"{name}.svg").write_text("\n".join(self.svg + ['</svg>']), encoding="utf-8")


def service():
    d = Diagram(1800, 1140, "DATA TADA 서비스 아키텍처", "중앙 FastAPI 서버가 분석 자료와 LLM을 연결합니다. 쿠버네티스와 독립 작업 큐는 사용하지 않습니다.")
    d.box(480, 155, 790, 645, "Cloud Run / Docker 컨테이너 1개 (배포 설계)", [], fill="#eaf6f8", stroke=TEAL, title_size=27)
    d.box(510, 230, 730, 100, "React 정적 화면", ["Vite 빌드 결과, FastAPI가 같은 주소에서 제공"])
    d.box(510, 355, 730, 170, "FastAPI + Uvicorn", ["입력 검증 → 분석 조회와 계산 → JSON 응답", "비교 4개 / 상세 3개, 최대 5개 후보", "요청 ID, 공통 오류, 생존/준비 확인, 응답시간"])
    d.box(510, 550, 730, 210, "페이지별 해설 서비스", ["필요한 근거 구성 → 캐시/생성 잠금 확인", "LLM 호출 → 형식과 근거 ID 검사 → DB 저장", "현재 페이지부터 생성, 모델/프롬프트별 캐시 분리", "키 미설정 시 비활성, 실패해도 지표 조회 유지"])
    d.box(45, 335, 330, 235, "사용자 브라우저", ["지도에서 후보 1~5개 선택", "카드 이동 / 표 비교", "상권 1개 상세와 차트", "하단 LLM 해설 표시"])
    d.box(45, 650, 330, 130, "배경지도 공급자", ["Leaflet → OSM 타일", "상권 선택 원은 경계 아님"])
    d.arrow([(375, 390), (510, 390)], "HTTPS 요청", (385, 350))
    d.arrow([(510, 465), (375, 465)], "화면 / JSON", (387, 477))
    d.arrow([(205, 650), (205, 570)], "브라우저 직접 통신", (75, 603))
    d.box(1390, 225, 365, 230, "Cloud SQL / MySQL", ["실제 상권 위치 목록", "과거/예측 분석 스냅샷", "매물, 메뉴, 자료 버전", "해설 캐시와 생성 잠금"])
    d.arrow([(1240, 390), (1390, 390)], "SQL 조회/저장", (1250, 348))
    d.arrow([(1390, 420), (1270, 420)], color=MUTED)
    d.box(1390, 550, 365, 190, "LLM provider", ["현재 OpenAI 연결 경계", "모델명은 환경변수로 교체", "현재 실제 호출은 비활성"], fill="#f3fbfb")
    d.arrow([(1240, 605), (1390, 605)], "HTTPS + 근거", (1250, 565))
    d.arrow([(1390, 680), (1240, 680)], "구조화 응답", (1260, 693))
    d.box(45, 880, 470, 185, "오프라인 Python 배치", ["원자료 정리와 지표 계산", "검증된 모델로 예측 후 DB 반영", "현재는 명시적인 가상 자료 import"])
    d.arrow([(515, 995), (1335, 995), (1335, 470), (1510, 470), (1510, 455)], "배치 반영, 사용자 요청마다 모델 학습 없음", (650, 965), dashed=True)
    d.box(570, 850, 650, 105, "개발 / 배포", ["GitHub → Docker 빌드 → Cloud Run, 현재 커밋/푸시 없음"])
    d.arrow([(895, 850), (895, 800)], "이미지 배포", (915, 810), dashed=True)
    d.box(1390, 840, 365, 220, "관측과 평가", ["현재: 구조화 로그, /metrics", "후속: Cloud Monitoring", "후속: OpenTelemetry", "후속: Langfuse 모델 비교"], dashed=True)
    d.arrow([(1270, 755), (1305, 755), (1305, 820), (1390, 820), (1390, 880)], dashed=True, color=MUTED)
    d.text(570, 1030, "실선: 구현한 통신 경로와 기본 코드", 18, MUTED)
    d.text(570, 1063, "점선: 후속 연결 / 배포 환경은 아직 검증하지 않음", 18, MUTED)
    d.save("service-architecture")


def llm():
    d = Diagram(1600, 1110, "페이지별 LLM 해설 실행 흐름", "고정된 서버 처리 순서입니다. 스스로 조사 도구를 선택하는 AI 에이전트는 현재 필요하지 않습니다.")
    d.box(50, 160, 400, 135, "1. 현재 페이지 표시", ["지표/차트를 먼저 조회", "비교는 선택 후보 전체 1~5개"])
    d.box(600, 160, 400, 135, "2. 근거 구성", ["페이지, 분기, 조건과 수치", "자료/모델/프롬프트 버전"])
    d.box(1150, 160, 400, 135, "3. DB 캐시 확인", ["근거와 설정의 해시로 조회", "완료 결과 또는 생성 잠금"])
    d.arrow([(450, 225), (600, 225)], "해설 POST", (470, 188))
    d.arrow([(1000, 225), (1150, 225)], "캐시 키", (1040, 188))
    d.box(1150, 390, 400, 165, "4. 캐시 미적중이면 생성", ["완료까지 HTTP 요청 유지", "동시 호출 제한과 timeout", "다른 동일 요청은 202로 대기"])
    d.arrow([(1350, 295), (1350, 390)], "미적중", (1370, 327))
    d.box(600, 390, 400, 165, "5. LLM provider", ["정해진 근거로 구조화 응답", "모델명 교체 가능", "현재는 실제 유료 호출 없음"])
    d.arrow([(1150, 470), (1000, 470)], "근거 전송", (1028, 433))
    d.box(50, 390, 400, 165, "6. 결과 검증", ["응답 형식과 근거 ID 검사", "의미/숫자 품질 평가는 별도", "유효한 완료 결과만 DB 저장"])
    d.arrow([(600, 470), (450, 470)], "생성 결과", (475, 433))
    d.box(50, 665, 400, 165, "7. 하단 해설 표시", ["다시 방문하면 캐시 재사용", "카드 화살표 이동은 재호출 안 함", "다른 페이지는 처음 열 때 생성"])
    d.arrow([(250, 555), (250, 665)], "완료 응답", (270, 596))
    d.arrow([(1550, 225), (1580, 225), (1580, 620), (450, 620), (450, 700)], "캐시 적중: LLM 호출 없이 반환", (950, 585), color=MUTED)
    d.box(600, 665, 400, 165, "오류 / 비활성 / 자료 없음", ["실패 상태와 안내 표시", "기본 지표와 차트는 계속 사용", "실패 결과를 완료 캐시에 넣지 않음"], fill="#fff5ec")
    d.arrow([(800, 555), (800, 665)], "거부 / 오류 / timeout", (820, 596), color="#d5783b")
    d.box(1150, 665, 400, 165, "후속 관측과 실험", ["요청 ID로 서버와 LLM 연결", "모델/프롬프트/토큰/시간 기록", "동일 평가셋으로 품질 비교"], dashed=True)
    d.box(50, 910, 1500, 140, "현재와 후속 범위", ["현재: 근거 구성, 기본 provider 경계, 캐시/잠금, 모의 실패 테스트, 서버 응답시간 기록", "후속: 실제 LLM 품질 평가, Langfuse와 OpenTelemetry 연결. 에이전트는 자유 질문/동적 도구 선택이 필요할 때 검토"])
    d.save("llm-flow")


if __name__ == "__main__":
    service()
    llm()
    print("Rendered architecture PNG/SVG pairs")
