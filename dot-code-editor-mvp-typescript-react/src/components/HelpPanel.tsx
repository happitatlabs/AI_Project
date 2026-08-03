type HelpPanelProps = {
  isOpen: boolean;
};

export function HelpPanel({ isOpen }: HelpPanelProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <section className="helpPanel" aria-label="Feature help">
      <div>
        <h2>도움말</h2>
        <p>이미지를 코드형 도트 자산으로 바꾸고, 팔레트 키와 sprite 문자열을 함께 export합니다.</p>
      </div>
      <div className="helpGrid">
        <div>
          <h3>팔레트</h3>
          <p>격자 위 팔레트에서 색상 키를 고릅니다. 색상칩을 누르면 현재 색상 기준 HSV 슬라이더로 색을 바꿀 수 있습니다.</p>
        </div>
        <div>
          <h3>도구</h3>
          <p>Paint는 선택 색상으로 칠하고, Erase는 0 투명색으로 지우며, Pick은 도트에서 색상 키를 가져옵니다.</p>
        </div>
        <div>
          <h3>편집</h3>
          <p>Undo/Redo, Clear, Flip, 이동 버튼은 sprite 문자열 데이터를 직접 바꿉니다.</p>
        </div>
        <div>
          <h3>투명 처리</h3>
          <p>Alpha only가 기본값입니다. 흰색/검은색은 자동으로 투명 처리하지 않고, 배경색 모드에서만 0으로 export합니다.</p>
        </div>
        <div>
          <h3>Export</h3>
          <p>오른쪽 Export 코드는 현재 팔레트와 sprite를 즉시 반영합니다. React 프로젝트에 그대로 붙여 넣을 수 있습니다.</p>
        </div>
      </div>
    </section>
  );
}
