CREATE OR REPLACE procedure P_BKCHNO -- 15 전표 작성
 (
  jAC_DATE     in varchar2, -- 전표일자
  jAC_CHITNO   in   number, -- 전표의뢰번호
  jCHK         in varchar2, -- 생성확인
  jOCCR_PART   in   number, -- 발생부문
  jACNT_DIV    in   number, -- 사업부문
  jDEPT_CD     in   number, -- 부서
  jINVOICE_NO  in varchar2, -- 인보이스No
  jTR_DATE     in varchar2, -- 거래, 이체일자
  jTR_DATE_SEQ in   number, -- 거래일자별일련번호
  jCHIT_RMK    in varchar2, -- 전표적요
  jINP_DATE    in varchar2, -- 입력일시
  jUPD_DATE    in varchar2 -- 작업일시
  )
IS
BEGIN
   DECLARE
      sysdt varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');

   BEGIN
      --- 2. 전표 의뢰내역 조회
      Declare
         w_CNTT                    NUMBER(03) := 0; -- 항번
         w_STATUS                VARCHAR2(20) := 'NEW'; -- 상태
         w_SET_OF_BOOKS_ID         NUMBER(15) := 2026; -- 원장ID
         w_USER_JE_SOURCE_NAME   VARCHAR2(25) := 'FINANCE'; -- 전표출처
         w_USER_JE_CATEGORY_NAME VARCHAR2(25) := ''; -- 전표범주(입금, 출금, 환차)
         w_GROUP_ID                NUMBER(15) := 101; -- 처리그룹 ID
         w_ACCOUNT_DATE            DATE       := to_date(iAC_DATE, 'yyyymmdd');
         w_ACTUAL_FLAG           VARCHAR2(01) := 'A'; -- 사실여부
         w_ENTERED_DR              NUMBER(15) := 0; -- 차변금액
         w_ENTERED_CR              NUMBER(15) := 0; -- 대변금액
         w_SEGMENT1              VARCHAR2(25) := ''; -- 사업부문
         w_SEGMENT2              VARCHAR2(25) := ''; -- 본부
         w_SEGMENT3              VARCHAR2(25) := ''; -- 부서
         w_SEGMENT4              VARCHAR2(25) := ''; -- 계정코드
         w_SEGMENT5              VARCHAR2(25) := ''; -- 계좌
         w_MNEY_UNIT             VARCHAR2(15) := 'KRW'; -- 화폐단위
         w_UPD_EMP               VARCHAR2(08) := '---ft_dept_emp(''1221'')'; -- 작업자 (재무회계팀)
         w_REFERENCE1            VARCHAR2(50) := ''; -- BATCH번호
         w_REFERENCE4            VARCHAR2(50) := iCHK || '-' || iAC_DATE; -- 차수-전표번호
         w_REFERENCE6            VARCHAR2(50) := ''; -- 순번
         w_REFERENCE10           VARCHAR2(50) := iCHIT_RMK; -- 적요
         
         CURSOR c1 is
            select CHK        , AC_DATE   , AC_CHITNO , HANG      ,
                   DC_FLAG    , ACNT_CD   , ACNT_NM   , CHIT_AMT  ,
                   BANK_CD    , ACNT_NO   , INVOICE_NO, TR_DATE   ,
                   TR_DATE_SEQ, MNEY_UNIT , OCCR_PART , UPD_EMP   ,
                   UPD_DATE
                from TN_BKCHIT
            where CHK       = iCHK
              and AC_DATE   = iAC_DATE
              and AC_CHITNO = iAC_CHITNO
            order by tr_date, tr_date_seq;
       
      Begin
         for clr in c1 loop -- 환차익 = 현재평가 - 원금
             -- 전표범주 (category)
             if clr.OCCR_PART = '입금' then
                w_USER_JE_CATEGORY_NAME := 'deposit';
             elsif clr.OCCR_PART = '출금' then
                w_USER_JE_CATEGORY_NAME := 'payment';
             elsif clr.OCCR_PART = '환차' then
                w_USER_JE_CATEGORY_NAME := 'exchange p/l';
             end if;
                
             if clr.DC_FLAG = '1' then
                w_ENTERED_DR := clr.CHIT_AMT;
                w_ENTERED_CR := 0;
             else
                w_ENTERED_DR := 0;
                w_ENTERED_CR := clr.CHIT_AMT;
             end if;

             if clr.ACNT_CD in ('1110101', '1110201') then -- 보통예금, 당좌예금
                w_SEGMENT1 := '01'; -- 사업부문
                w_SEGMENT2 := iDEPT_CD; -- 부서
                w_SEGMENT3 := clr.ACNT_CD; -- 계정코드
                w_SEGMENT4 := clr.ACNT_NO; -- 계좌번호
                w_SEGMENT5 := '000';
             elsif clr.ACNT_CD in ('1110301') then -- 외화예금
                w_SEGMENT1 := '01';
                w_SEGMENT2 := iDEPT_CD;
                w_SEGMENT3 := clr.ACNT_CD;
                w_SEGMENT4 := clr.ACNT_NO;
                w_SEGMENT5 := '000';
             elsif clr.ACNT_CD in ('4110101', '4210101') then -- 외환차익, 외환차손
                w_SEGMENT1 := '01';
                w_SEGMENT2 := iDEPT_CD;
                w_SEGMENT3 := clr.ACNT_CD;
                w_SEGMENT4 := clr.ACNT_NO;
                w_SEGMENT5 := '000';
             elsif clr.ACNT_CD in ('2110101') then -- 가수금
                w_SEGMENT1 := '01';
                w_SEGMENT2 := iDEPT_CD;
                w_SEGMENT3 := clr.ACNT_CD;
                w_SEGMENT4 := '00000000000000'; -- 관리항목
                w_SEGMENT5 := '000';
             end if;             
             --- 1.1 GL interface 차변
             begin
                insert into GL_INTERFACE(
                            STATUS        , SET_OF_BOOKS_ID, ACCOUNT_DATE   , USER_JE_SOURCE_NAME,
                            USER_JE_CATEGORY_NAME, GROUP_ID, CODE_COMBINATION_ID, SEGMENT1   ,
                            SEGMENT2      , SEGMENT3       , SEGMENT4       , SEGMENT5       ,
                            SEGMENT6      , SEGMENT7       , SEGMENT8       , SEGMENT9       ,
                            ENTERED_DR    , ENTERED_CR     , CURRENCY_CODE  , DATA_CREATED   ,
                            CREATED_BY    , ACTUAL_FLAG    , REFERENCE1     , REFERENCE4     ,
                            REFERENCE6    , REFERENCE10
                            )
                    values (
                            w_STATUS      , w_SET_OF_BOOKS_ID, w_ACCOUNT_DATE , w_USER_JE_SOURCE_NAME,
                            w_USER_JE_CATEGORY_NAME, w_GROUP_ID, null         , w_SEGMENT1   ,
                            w_SEGMENT2    , w_SEGMENT3       , w_SEGMENT4     , w_SEGMENT5   ,
                            null          , null             , null           , null         ,
                            w_ENTERED_DR  , w_ENTERED_CR     , w_MNEY_UNIT    , sysdate      ,
                            w_UPD_EMP     , w_ACTUAL_FLAG    , w_REFERENCE1   , w_REFERENCE4 ,
                            w_REFERENCE6  , w_REFERENCE10
                            );
             end;
             
             --- 1.2 GL interface 대변
             begin
                insert into GL_INTERFACE(
                            STATUS        , SET_OF_BOOKS_ID, ACCOUNT_DATE   , USER_JE_SOURCE_NAME,
                            USER_JE_CATEGORY_NAME, GROUP_ID, CODE_COMBINATION_ID, SEGMENT1   ,
                            SEGMENT2      , SEGMENT3       , SEGMENT4       , SEGMENT5       ,
                            SEGMENT6      , SEGMENT7       , SEGMENT8       , SEGMENT9       ,
                            ENTERED_DR    , ENTERED_CR     , CURRENCY_CODE  , DATA_CREATED   ,
                            CREATED_BY    , ACTUAL_FLAG    , REFERENCE1     , REFERENCE4     ,
                            REFERENCE6    , REFERENCE10
                            )
                     values (
                            w_STATUS      , w_SET_OF_BOOKS_ID, w_ACCOUNT_DATE, w_USER_JE_SOURCE_NAME,
                            w_USER_JE_CATEGORY_NAME, w_GROUP_ID, null        , w_SEGMENT1    ,
                            w_SEGMENT2    , w_SEGMENT3       , w_SEGMENT4    , w_SEGMENT5    ,
                            null          , null             , null          , null          ,
                            w_ENTERED_DR  , w_ENTERED_CR     , w_MNEY_UNIT   , sysdate       ,
                            w_UPD_EMP     , w_ACTUAL_FLAG    , w_REFERENCE1  , w_REFERENCE4  ,
                            w_REFERENCE6  , w_REFERENCE10
                            );
             end;

         end loop;
         <<loop_skip>>
           null;
      End;
     <<end_p>>
      null;
   END;
END P_BKCHNO;
