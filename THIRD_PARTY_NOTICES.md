# 제3자 고지

아래 라이선스 표기는 일반 정보이며, 배포본의 라이선스 원문을 확인하기 전입니다. 저장소 포함 여부는 이 저장소의 현재 파일 기준입니다.

## 모델·사전·글꼴

| 항목 | 출처·버전 | 라이선스 표기 | 저장소 포함 | 출처 |
|---|---|---|---|---|
| `ch_PP-OCRv5_det_mobile` (ONNX) | PP-OCRv5 / RapidOCR v3.10.0 | Apache-2.0 | 아니오 | [ModelScope 파일](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx) |
| `korean_PP-OCRv5_rec_mobile` (ONNX) | PP-OCRv5 / RapidOCR v3.10.0 | Apache-2.0 | 아니오 | [ModelScope 파일](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/korean_PP-OCRv5_rec_mobile.onnx) |
| 한국어 문자 사전 | PaddleOCR v3.3.2 | Apache-2.0 | 아니오 | [PaddleOCR 사전 파일](https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/v3.3.2/ppocr/utils/dict/ppocrv5_korean_dict.txt) |
| Nanum Gothic / Nanum Myeongjo / Nanum Gothic Coding (합성 평가용) | google/fonts 커밋 `1c96438dec81b2b5078557d91315e31fb29b9462` | SIL OFL 1.1 | 아니오 | [google/fonts 커밋](https://github.com/google/fonts/tree/1c96438dec81b2b5078557d91315e31fb29b9462) |
| Noto Sans KR subset (`demo/frontend`) | Version 2.004-H2; Copyright Adobe 2014-2021; Reserved Font Name 'Source' | SIL OFL 1.1 | 예 | [저작권 고지](demo/frontend/src/assets/fonts/NotoSansKR/OFL.txt), [OFL 원문](https://openfontlicense.org) |
| Noto Serif KR subset (`demo/frontend`) | Version 2.003-H1; Copyright Adobe 2017-2024 | SIL OFL 1.1 | 예 | [저작권 고지](demo/frontend/src/assets/fonts/NotoSerifKR/OFL.txt), [OFL 원문](https://openfontlicense.org) |

두 Noto 글꼴의 저장소 포함 파일은 각 글꼴 디렉터리의 저작권 고지와 [OFL 원문](https://openfontlicense.org)을 함께 확인하세요. Noto Sans KR 서브셋에서 Reserved Font Name을 사용한 방식이 OFL 조건에 맞는지는 확인이 필요합니다.

## Python 패키지

설치 버전은 프로젝트의 설치 환경에서 확인한 값입니다. 아래 라이선스 열은 onnxruntime과 scikit-learn만 확인된 정보이며, 나머지는 배포본에서 확인이 필요합니다.

| 패키지 | 버전 | 라이선스 정보 |
|---|---:|---|
| onnxruntime | 1.31.1 | MIT |
| numpy | 2.5.4 | 배포본에서 확인 필요 |
| opencv-python-headless | 4.14.0.94 | 배포본에서 확인 필요 |
| pyclipper | 1.4.0 | 배포본에서 확인 필요 |
| python-dotenv | 1.2.4 | 배포본에서 확인 필요 |
| scikit-learn | 1.7.2 | BSD-3-Clause |
| pymupdf | 2.1 | 배포본에서 확인 필요 |
| pydantic | 2.14.3 | 배포본에서 확인 필요 |
| pillow | 13.0.0 | 배포본에서 확인 필요 |
| fastapi | 0.162.4 | 배포본에서 확인 필요 |
| uvicorn | 0.54.0 | 배포본에서 확인 필요 |
| sqlmodel | 0.0.44 | 배포본에서 확인 필요 |
| python-multipart | 0.0.33 | 배포본에서 확인 필요 |
| httpx | 0.28.1 | 배포본에서 확인 필요 |

PyMuPDF는 AGPL-3.0 또는 상용 라이선스를 선택하는 이중 라이선스로 알려져 있습니다. 공개 저장소와 기관 배포에 적용할 조건을 확인할 필요가 있습니다. 여기서는 판단이나 결론을 제시하지 않습니다.
