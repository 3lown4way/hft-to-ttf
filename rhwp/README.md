# rhwp KICE workspace

이 디렉터리는 평가원/이감 시험지 재조판에 사용하는 rhwp 작업 환경을 영구 보존하기 위한 공간입니다.

## 구성

- `upstream/` — `edwardkim/rhwp`를 git submodule로 고정한 원본 소스
- `scripts/bootstrap.sh` — submodule 초기화 후 현재 hft-to-ttf 저장소의 TTF를 rhwp 작업용 폰트 디렉터리에 연결
- `notes/previous-session.md` — 이전 세션에서 확인한 수정 상태와 이어서 할 작업

현재 upstream pin은 rhwp v0.8.4의 commit `496333b27d21ddb9114ba9ae340bcb895870c9a7`입니다.

## 시작

```bash
git submodule update --init rhwp/upstream
bash rhwp/scripts/bootstrap.sh
```

그 다음 rhwp 소스 수정은 이 저장소의 별도 브랜치에서 진행하고, KICE/HFT 전용 변경은 `rhwp/patches/` 또는 직접 소스 변경으로 남깁니다.

부모 저장소의 `output_ttf/`가 HFT 변환 폰트의 기준 위치입니다.
