# Dot Code Editor MVP

이미지를 브라우저 안에서 픽셀화하고, 도트 에디터처럼 수정한 뒤, 최종 결과를 TypeScript 코드로 내보내는 웹앱입니다. PNG/WebP 자산을 저장하는 도구가 아니라 `sprite` 문자열 배열, `palette` 객체, `PixelSprite` React 렌더러로 다룰 수 있는 코드형 도트 자산을 만드는 것이 목적입니다.

## 실행 방법

```bash
npm install
npm run dev
```

Vite가 출력하는 로컬 주소를 브라우저에서 엽니다. 예: `http://127.0.0.1:5175/`

프로덕션 빌드는 아래 명령으로 확인합니다.

```bash
npm run build
```

## 이미지 업로드 방법

1. 왼쪽 `Input` 패널의 `Image` 파일 선택 버튼을 누릅니다.
2. PNG, JPG, WebP 이미지를 선택합니다.
3. 필요한 경우 `Grid size`와 `Palette limit`을 조정합니다.
4. `Convert Image`를 누르면 브라우저 메모리 안에서 Canvas로 픽셀화됩니다.

원본 이미지는 서버로 업로드되지 않으며 프로젝트의 assets 폴더에도 저장되지 않습니다.
변환 크기는 `16x16`, `24x24`, `32x32`, `48x48`, `64x64`를 지원합니다. `48x48`은 RPG Maker MV 캐릭터 스프라이트, `64x64`는 큰 캐릭터/아이템 도트 편집용입니다.
팔레트 제한은 `4`, `8`, `16`, `32 colors`를 지원합니다. 기본값은 `32x32 / 16 colors`이며, `32 colors`는 디테일이 많은 도트풍 이미지를 보존하기 위한 옵션입니다.
Canvas 변환은 nearest neighbor 방식으로 처리하며 안티앨리어싱을 적용하지 않습니다.

## Transparency Mode

변환 시 투명 처리 방식은 `Transparency mode`에서 선택합니다.

- `Alpha only`: 원본 alpha 값이 `0`인 픽셀만 `0` transparent로 export합니다. 기본값입니다.
- `No transparency`: 모든 픽셀을 색상으로 유지합니다. JPG 이미지에 권장합니다.
- `Corner color`: 출력 격자의 네 모서리 대표 색상을 배경색으로 추정하고, tolerance 이내인 픽셀만 `0` transparent로 export합니다.
- `Manual background color`: `Pick background`를 누른 뒤 원본 미리보기에서 배경 픽셀을 직접 선택합니다. tolerance 슬라이더로 허용 범위를 조정합니다.

흰색이나 검은색을 자동으로 transparent로 바꾸지 않습니다. 실제 흰색은 `#ffffff`, 실제 검은색은 `#000000` 또는 근접 색상으로 팔레트에 남을 수 있습니다.

## 샘플 불러오기

파일 업로드 없이 앱을 확인하려면 왼쪽 패널의 `샘플 불러오기` 버튼을 누릅니다. 16x16 임시 도트 캐릭터가 로드되고, 팔레트/미리보기/export 코드가 바로 갱신됩니다.

## 도트 수정 방법

- `Paint`: 현재 선택된 팔레트 색상으로 도트를 칠합니다.
- `Erase`: 도트를 투명색 `0`으로 지웁니다.
- `Pick`: 클릭한 도트의 색상 키를 선택합니다.
- 도트 격자 바로 위 팔레트에서 번호를 누르면 현재 칠하기 색상이 바뀝니다.
- 팔레트의 색상칩을 누르면 색상 선택 모달이 열립니다.
- 모달은 현재 색상을 기준으로 Hue/Saturation/Value 슬라이더 위치를 맞춰 엽니다.
- 모달에서 색상을 바꾸면 같은 키를 쓰는 모든 도트 색상과 export 코드가 즉시 바뀝니다.
- 격자 위에서 드래그하면 여러 칸을 연속으로 칠할 수 있습니다.

## 도움말

상단 `도움말` 버튼을 누르면 팔레트, 도구, 편집, Export 기능 설명을 앱 안에서 확인할 수 있습니다.

## Undo 사용 방법

- `Undo`: 직전 도트 편집, 초기화, 반전, 이동 작업을 되돌립니다.
- `Redo`: 되돌린 작업을 다시 실행합니다.

새 편집이 발생하면 redo 기록은 초기화됩니다.

## Copy Sprite Only 사용 방법

오른쪽 `Export` 패널 아래의 `Copy Sprite Only` 버튼을 누르면 현재 스프라이트 문자열 배열만 클립보드에 복사됩니다.

복사되는 형태:

```ts
export const sprite = [
  "0000000000000000",
  "0000011111000000",
];
```

## Export 코드 사용 방법

`Copy TS Code` 또는 `Download .ts`로 전체 TypeScript 코드를 가져옵니다. 포함 내용은 다음과 같습니다.

- `palette` 객체
- `sprite` 문자열 배열
- `PixelSprite` React 컴포넌트

다른 React 프로젝트에서 아래처럼 사용할 수 있습니다.

```tsx
import { PixelSprite, palette, sprite } from "./pixel-sprite";

export function Character() {
  return <PixelSprite sprite={sprite} palette={palette} pixelSize={8} />;
}
```

`pixelSize`를 바꾸면 같은 데이터로 렌더링 크기만 조정할 수 있습니다.

## Happitat Labs 웹 배포

`https://happitatlabs.com/products/dot-code-editor` 경로에 붙일 때는 전용 base path로 빌드합니다.

```bash
npm run build:happitat
```

정적 호스팅에 `dist` 폴더의 내용을 `/products/dot-code-editor/` 경로로 업로드합니다. 앱 자산은 `/products/dot-code-editor/assets/...` 기준으로 참조됩니다.

운영자에게 zip 파일로 넘길 때는 아래 명령을 실행합니다.

```bash
npm run package:happitat
```

생성 파일:

```text
web-output/dot-code-editor-happitat-web.zip
```

서버 조건:

- `/products/dot-code-editor/`에서 `index.html`을 서빙해야 합니다.
- `/products/dot-code-editor/assets/` 하위 정적 파일을 그대로 제공해야 합니다.
- 현재 앱은 서버 API 없이 브라우저 안에서만 동작하므로 별도 백엔드, 인증, 파일 업로드 서버가 필요 없습니다.

## Cloudflare Workers 데모 배포

`https://sql-diagnoser-demo.pletta900114.workers.dev/` 같은 `workers.dev` 데모 URL로 붙일 때는 Cloudflare Workers 정적 자산 배포를 사용합니다.

로컬 Workers 프리뷰:

```bash
npm run workers:dev
```

Cloudflare 로그인 또는 `CLOUDFLARE_API_TOKEN` 설정 후 공개 데모 배포:

```bash
npm run deploy:workers
```

현재 Worker 이름은 `wrangler.jsonc`의 `dot-code-editor-demo`입니다. 배포 후 URL은 Cloudflare 계정의 workers.dev 서브도메인에 따라 아래 형태가 됩니다.

```text
https://dot-code-editor-demo.<account-subdomain>.workers.dev/
```

예시 계정 서브도메인이 `pletta900114`라면 예상 URL은 아래와 같습니다.

```text
https://dot-code-editor-demo.pletta900114.workers.dev/
```

Workers 설정은 `dist` 정적 파일을 제공하고, SPA fallback으로 없는 경로도 `index.html`을 반환하도록 구성되어 있습니다.

## 콘솔/브라우저와 Android 앱 전환

같은 React/Vite 코드베이스를 두 방식으로 사용합니다.

- 콘솔/브라우저 작업: `npm run dev`
- Cloudflare Workers 데모: `npm run deploy:workers`
- Happitat 웹 패키지: `npm run package:happitat`
- Android 앱 패키징: `npm run android:apk:local`
- 연결된 Android 기기에 설치: `npm run android:install:local`

## Android APK 빌드

이 프로젝트는 Capacitor로 Android WebView 앱을 생성할 수 있게 설정되어 있습니다.

앱 정보:

- 앱 이름: `픽셀 정비소`
- Android applicationId: `com.pixelgarage.editor`
- 웹 빌드 디렉터리: `dist`
- 화면 방향: 세로/가로 회전 허용, `android:screenOrientation="fullUser"`

웹앱을 Android 프로젝트에 동기화하려면 아래 명령을 실행합니다.

```bash
npm run android:sync
```

Android Studio에서 열려면 아래 명령을 실행합니다.

```bash
npm run android:open
```

이 PC에서는 프로젝트 로컬 Android SDK와 `C:\Program Files\Android\openjdk\jdk-21.0.8`을 사용해 debug APK를 만들 수 있습니다.

```bash
npm run android:apk:local
```

성공 시 APK는 아래 경로에 복사됩니다.

```text
apk-output/pixel-garage-debug.apk
```

Gradle 원본 산출물은 아래에도 남습니다.

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

USB 디버깅이 켜진 Android 기기를 연결한 뒤 설치하려면 아래 명령을 실행합니다.

```bash
npm run android:install:local
```

## 검증 스크린샷

검증 스크린샷은 아래 경로에 저장합니다.

- `docs/screenshots/app-loaded.png`
- `docs/screenshots/editor-after-click.png`
- `docs/screenshots/export-panel.png`

## 최종 검증 명령 기록

2026-06-23 기준으로 아래 명령을 다시 실행했습니다.

```bash
npm install
```

결과: 정상 종료, `up to date`, `found 0 vulnerabilities`

```bash
npm run build
```

결과: 정상 종료, TypeScript 빌드 및 Vite 프로덕션 빌드 성공

```bash
npm audit --audit-level=high
```

결과: 정상 종료, `found 0 vulnerabilities`

2026-08-03 기준 Cloudflare Workers 데모 배포 구성 검증:

```bash
npm run build:workers
```

결과: 정상 종료, Vite 정적 빌드 성공

```bash
npx wrangler deploy --dry-run
```

결과: 정상 종료, `dist` 정적 자산 4개를 읽고 dry-run 완료

2026-06-23 기준 Android 패키징 검증:

```bash
npm run android:sync
```

결과: 정상 종료, Vite 빌드 후 Android assets 동기화 성공

```bash
npm run android:apk
```

결과: 초기에는 `JAVA_HOME is not set and no 'java' command could be found in your PATH.` 오류로 중단

이후 로컬 Android SDK와 기존 설치된 JDK 경로를 사용하도록 구성한 뒤 아래 명령을 실행했습니다.

```bash
npm run android:apk:local
```

결과: 정상 종료, APK 생성 성공

생성 파일:

```text
apk-output/pixel-garage-debug.apk
```

APK 정보:

- package: `com.pixelgarage.editor`
- app label: `픽셀 정비소`
- minSdk: `24`
- targetSdk: `36`
- size: `4,275,762 bytes`
- SHA-256: `E6A8CADE078D76B7FAA8BC06428E8AD713F91A71143D07AE357B2A5B07D29C31`
- signature verify: APK Signature Scheme v2 정상

## 현재 제한사항

- 이미지 처리는 브라우저 내 Canvas API만 사용합니다.
- 서버 저장, 로그인, 원격 업로드 기능은 없습니다.
- 색상 양자화는 MVP용 median-cut 방식이며 전문 그래픽 툴 수준의 보정 기능은 없습니다.
- 모바일 폭에서도 깨지지 않게 정리했지만, 주 사용 환경은 데스크톱입니다.
- Export 컴포넌트는 기본 렌더러이며 애니메이션, 타일맵, 레이어 기능은 포함하지 않습니다.
- 현재 APK는 debug 빌드입니다. 배포용 release APK/AAB에는 별도 서명 키가 필요합니다.
