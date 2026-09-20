/**
 * 서식5 행정정보 공동이용 사전동의서.
 *
 * 문구는 시행지침 p.28 원문 그대로. 원문은 서명란에 "(서명 또는 인)"과
 * "신청자 본인 작성 자필서명 후 첨부"를 요구한다.
 *
 * 데모는 이를 **전자서명**으로 대체해 "수기 0건"을 보여주되, 현행 지침과 다르다는
 * 점을 배지로 드러내고 자필 스캔 업로드 모드도 함께 남긴다.
 * (TF 확인사항: 전자서명 대체 가능 여부)
 *
 * ※ 공동이용 행정정보 코드가 공고문(371)과 시행지침(46+388)에서 다르다.
 *   여기서는 공고문 값을 쓴다 — 이것도 TF 확인사항.
 */

import SignaturePad from '../components/SignaturePad.tsx'
import { Cell, DateTriple, FormSheet, FormTable, Radio, Text } from './FormSheet.tsx'
import { SIGN_MODES, type Form5Value, type SignMode } from './form5-model.ts'

const COLS = [100]

interface Props {
  value: Form5Value
  onChange: (v: Form5Value) => void
  signMode: SignMode
  onSignModeChange: (m: SignMode) => void
}

export default function Form5AdminInfoConsent({
  value,
  onChange,
  signMode,
  onSignModeChange,
}: Props) {
  const set =
    <K extends keyof Form5Value>(k: K) =>
    (next: Form5Value[K]) =>
      onChange({ ...value, [k]: next })

  return (
    <FormSheet formNo="서식5" title="행정정보 공동이용 사전동의서">
      <FormTable cols={COLS}>
        <tr>
          <Cell center>
            <strong style={{ fontSize: 18 }}>행정정보 공동이용 사전동의서</strong>
          </Cell>
        </tr>
        <tr>
          <Cell>
            <div style={{ lineHeight: 1.9 }}>
              <div>1. 이용기관 명칭 : 전북특별자치도, 시군, 읍면동 행정복지센터</div>
              <div>
                2. 이용목적 : 전북청년 함께 두배적금 사업 대상자 선정 후 모니터링(거주 확인)
                목적
              </div>
              <div>
                3. 공동이용 행정정보(구비서류) :{' '}
                <span style={{ color: '#c00' }}>371(주민등록표 등·초본 A형)</span>
              </div>
              <div style={{ fontWeight: 700 }}>4. 정보주체(본인) 동의사항</div>
              <div style={{ paddingLeft: 12 }}>
                ○ 본인은 위 사무의 처리를 위하여 「전자정부법」제36조에 따른 행정정보
                공동이용을 통해 이용기관의 업무처리담당자가 전자적으로 본인의
                구비서류(공동이용 행정정보)를 확인하는 것에 동의합니까?
              </div>
            </div>
          </Cell>
        </tr>
        <tr>
          <Cell center>
            <span style={{ display: 'inline-flex', gap: 40 }}>
              {['동의함', '동의하지 않음'].map((opt) => (
                <label key={opt} className="form-check">
                  <Radio
                    name="form5-agree"
                    checked={value.agree === opt}
                    onPick={(next) => set('agree')(next ? opt : '')}
                  />
                  <span>{opt}</span>
                </label>
              ))}
            </span>
          </Cell>
        </tr>
        <tr>
          <Cell>
            <p style={{ margin: 0, lineHeight: 1.9 }}>
              ※ 만일, 본인이 위 행정정보 이용에 대해 동의를 하지 아니할 경우에도 불이익은
              없습니다. 다만, 동의하지 아니한 경우에는 본인이 해당 구비서류를 본인이 제출하여야
              합니다.
            </p>
          </Cell>
        </tr>
        <tr>
          <Cell center>
            <DateTriple
              ariaPrefix="작성일"
              value={value.writtenOn}
              onChange={set('writtenOn')}
            />
          </Cell>
        </tr>
      </FormTable>

      {/* 서명 영역 — 원문의 "성명 ___ (서명 또는 인)" 자리 */}
      <FormTable cols={COLS}>
        <tr>
          <Cell>
            <div style={{ maxWidth: 560, marginLeft: 'auto' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  marginBottom: 10,
                }}
              >
                <span style={{ whiteSpace: 'nowrap', paddingTop: 4 }}>성　　명 :</span>
                <span style={{ width: 140, paddingTop: 4 }}>
                  <Text ariaLabel="성명" value={value.name} onChange={set('name')} />
                </span>
                <span style={{ paddingTop: 4 }}>(서명 또는 인)</span>
              </div>

              <div style={{ marginBottom: 10 }}>
                <div style={{ marginBottom: 6 }}>
                  <span style={{ display: 'inline-flex', gap: 18 }}>
                    {SIGN_MODES.map((m) => (
                      <label key={m} className="form-check">
                        <input
                          type="radio"
                          name="form5-sign-mode"
                          checked={signMode === m}
                          onChange={() => onSignModeChange(m)}
                        />
                        <span>{m}</span>
                      </label>
                    ))}
                  </span>
                  <span className="badge-proposal">
                    현행 지침은 자필서명 — 전자서명 전환 제안
                  </span>
                </div>

                {signMode === '전자서명' ? (
                  <SignaturePad value={value.signature} onChange={set('signature')} />
                ) : (
                  <div>
                    <input
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png"
                      aria-label="자필서명 스캔본"
                      onChange={(e) =>
                        set('handwrittenFileName')(e.target.files?.[0]?.name ?? '')
                      }
                    />
                    {value.handwrittenFileName && (
                      <p className="form-basis">{value.handwrittenFileName}</p>
                    )}
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <span style={{ whiteSpace: 'nowrap' }}>생년월일 :</span>
                <DateTriple ariaPrefix="생년월일" value={value.birth} onChange={set('birth')} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ whiteSpace: 'nowrap' }}>전화번호 :</span>
                <span style={{ width: 180 }}>
                  <Text ariaLabel="전화번호" type="tel" value={value.phone} onChange={set('phone')} />
                </span>
              </div>
            </div>

            <div className="form-sheet__closing" style={{ paddingBottom: 0 }}>
              <p>
                <strong>전북특별자치도지사 · ○○ 시장 · 군수 귀하</strong>
              </p>
            </div>
          </Cell>
        </tr>
      </FormTable>

      {/* 원문이 아니라 데모가 덧붙인 주석이다. 서식 표 바깥에 둬서 원문과 섞이지
          않게 한다. 공동이용 행정정보 코드가 두 문서에서 다르다는 사실을 숨기고
          어느 한쪽을 조용히 고르면, 나중에 잘못된 값으로 굳는다. */}
      <div className="form-sheet__assumption">
        <p>
          ※ 공동이용 행정정보 코드가 공고문(371 주민등록표 A형)과 시행지침(46
          건강보험자격득실확인서 A형 + 388 주민등록표 J형)에서 다릅니다. 위 화면은
          공고문 값을 썼습니다. 어느 쪽이 유효한지는 TF 확인이 필요합니다.{' '}
          <strong>(데모 추정치)</strong>
        </p>
        <p>
          ※ 원문은 이 서식에 자필서명을 요구합니다. 데모는 전자서명 + 동의 시각·IP
          기록으로 갈음했습니다. 전자서명 대체 가능 여부도 TF 확인이 필요합니다.{' '}
          <strong>(데모 추정치)</strong>
        </p>
      </div>
    </FormSheet>
  )
}
