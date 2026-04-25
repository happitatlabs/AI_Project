CREATE OR REPLACE--12
procedure P_FOROUT-- 출금시 선입선출에 의한 환자전표생성 환차손  / 외화예금
                  --                                     외화예금/ 환차익
(job           in varchar2,
 jBANK_CD      in varchar2, -- 은행
 jACNT_NO      in varchar2, -- 계좌
 jTR_DATE      in varchar2, -- 출금일
 jTR_DATE_SEQ  in   number, -- 출금일련번호
 jACCT_SEQ     in varchar2, -- 계좌일련번호
 jMNEY_UNIT    in varchar2, -- 화폐단위
 jTR_AMT       in   number, -- 외화출금액
 jEXCH_RATE    in   number, -- 환율
 jOUT_AMT      in   number, -- 출금원화금액
 jAC_DATE      in varchar2, -- 전표일자
 jAC_CHITNO    in   number, -- 전표번호
 jUPD_EMP      in varchar2, -- 작업자
 jUPD_DATE     in varchar2) -- 작업일시
is
BEGIN
    DECLARE
        sysdt         varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
        w_OCCR_PART   varchar2(08) := '환차';
        w_BANK_CD     varchar2(07) := jBANK_CD; -- 출금은행코드
        w_ACNT_NO     varchar2(20) := jACNT_NO; -- 출금계좌
        w_ACNO_ACCT   varchar2(10) := '';--ft_acno_acct(w_ACNT_NO); -- 출금계좌의 계정코드
        w_PLUS_ACCT   varchar2(10) := ft_acnt_cd2('환차익');
        w_MINUS_ACCT  varchar2(10) := ft_acnt_cd2('환차손');
        w_HANG          number(04) := 0;
        w_CHIT_AMT      number(15) := 0;

        w_ACNT_CD1    varchar2(10) := ''; -- 미지급금 계정코드
        w_ACNT_NM1    varchar2(10) := ft_acnt_nm2(w_ACNT_CD1); -- 미지급금 계정명
        w_ACNT_CD2    varchar2(10) := '';--ft_acno_acct(jTRAN_JI_ACCT_NB); -- 출금계좌 계정코드
        w_ACNT_NM2    varchar2(10) := ft_acnt_nm2(w_ACNT_CD2); -- 출금계좌 계정명
        w_INVOICE_NO  varchar2(50) := jACCT_SEQ;
        w_MNEY_UNIT   varchar2(05) := jMNEY_UNIT;
        w_UPD_EMP     varchar2(08) := '';--ft_dept_emp('2221');

    BEGIN
        if ft_dbcheck('I_FORINS_B') = 'INVALID' then
            Raise_Application_Error(-20001, 'I_FORINS_B object INVALID Error!');
        end if;
        if ft_dbcheck('I_FOROUT') = 'INVALID' then
            Raise_Application_Error(-20001, 'I_FOROUT object INVALID Error!');
        end if;

        if job = 'D' then -- 출금상세내역 삭제시 (-)전표 생성
            Declare
                w_CNTT NUMBER(03) := 0; -- 항번
                CURSOR dl is
                    SELECT BANK_CD    ,ACNT_NO    ,TR_DATE      ,TR_DATE_SEQ  ,
                           ACCT_SEQ   ,TR_DATE0   ,TR_DATE_SEQ0 ,MNEY_UNIT    ,
                           OUTF_AMT   ,EXCH_RATE  ,OUT_AMT      ,RMN_FAMT     ,
                           RMN_AMT    ,EXCH_RATE0 ,OUT_AMT0     ,GAP_AMT      ,
                           AC_DATE    ,AC_CHITNO  ,HANG         ,UPD_EMP      ,
                           UPD_DATE
                    from TN_FOROUD
                    where BANK_CD     = jBANK_CD
                      and ACNT_NO     = jACNT_NO
                      and TR_DATE     = jTR_DATE
                      and TR_DATE_SEQ = jTR_DATE_SEQ
                      and GAP_AMT <> 0
                    order by tr_date0, tr_date_seq0;
            Begin
                for dlr in dl loop -- 환차익 = 현재평가 - 원금
                    -- 1. 전표 생성 후 삭제
                    -- 1.1 (-)전표 생성--------------------------->
                    if dlr.GAP_AMT > 0 then --외화예금/ 환차익
                        w_ACNT_CD1 := w_ACNO_ACCT;
                        w_ACNT_CD2 := w_PLUS_ACCT;
                        w_ACNT_NM1 := ft_acnt_nm2(w_ACNT_CD1); -- 외화예금 계정명
                        w_ACNT_NM2 := ft_acnt_nm2(w_ACNT_CD2); -- 환차익 계정명
                    else
                        w_ACNT_CD1 := w_MINUS_ACCT;
                        w_ACNT_CD2 := w_ACNO_ACCT;
                        w_ACNT_NM1 := ft_acnt_nm2(w_ACNT_CD1); -- 환차손 계정명
                        w_ACNT_NM2 := ft_acnt_nm2(w_ACNT_CD2); -- 외화예금 계정명
                    end if;
                    
                    w_HANG := w_HANG + 1;
                    w_CHIT_AMT := dlr.GAP_AMT * -1;
                    begin
                        insert into TN_BKCHIT (
                            AC_DATE   , AC_CHITNO  , HANG     , DC_FLAG    ,
                            ACNT_CD   , ACNT_NM    , CHIT_AMT , BANK_CD    ,
                            ACNT_NO   , INVOICE_NO , TR_DATE  , TR_DATE_SEQ,
                            MNEY_UNIT , OCCR_PART  , UPD_EMP  , UPD_DATE   )
                        values (
                            jAC_DATE    , jAC_CHITNO   , w_HANG      , '1'         ,
                            w_ACNT_CD1  , w_ACNT_NM1   , w_CHIT_AMT  , w_BANK_CD   ,
                            w_ACNT_NO   , w_INVOICE_NO , jTR_DATE    , jTR_DATE_SEQ,
                            w_MNEY_UNIT , w_OCCR_PART  , w_UPD_EMP   , sysdt      );
                    end;

                    w_HANG := w_HANG + 1;
                    begin
                        insert into TN_BKCHIT (
                            AC_DATE   , AC_CHITNO  , HANG     , DC_FLAG    ,
                            ACNT_CD   , ACNT_NM    , CHIT_AMT , BANK_CD    ,
                            ACNT_NO   , INVOICE_NO , TR_DATE  , TR_DATE_SEQ,
                            MNEY_UNIT , OCCR_PART  , UPD_EMP  , UPD_DATE   ) 
                        values (
                            jAC_DATE    , jAC_CHITNO   , w_HANG     , '2'         ,
                            w_ACNT_CD2  , w_ACNT_NM2   , w_CHIT_AMT , w_BANK_CD   ,
                            w_ACNT_NO   , w_INVOICE_NO , jTR_DATE   , jTR_DATE_SEQ,
                            w_MNEY_UNIT , w_OCCR_PART  , w_UPD_EMP  , sysdt      );
                    end;
                    
                    -- 1.2 삭제
                    begin
                        delete TN_FOROUD
                        where BANK_CD      = jBANK_CD
                          and ACNT_NO      = jACNT_NO
                          and TR_DATE      = jTR_DATE
                          and TR_DATE_SEQ  = jTR_DATE_SEQ
                          and ACCT_SEQ     = dlr.ACCT_SEQ
                          and TR_DATE0     = dlr.TR_DATE0
                          and TR_DATE_SEQ0 = dlr.TR_DATE_SEQ0;
                    end;
                end loop;

                begin
                    update TN_BKCHNO set
                           CHK = nvl(CHK, '0') + 1 -- 전표추가
                    where AC_DATE   = jAC_DATE
                      and AC_CHITNO = jAC_CHITNO;
                end;
                goto end_p;
            End;
        end if;

        --- 2. 해당계좌의 입금 조회
        Declare
            w_CNTT         NUMBER(03)   := 0; -- 항번
            w_Fjan         NUMBER(18,2) := jTR_AMT; -- 외화출금액
            w_OUTF_AMT     NUMBER(18,2) := 0; -- 건별외화출금
            w_OUT_AMT      NUMBER(15)   := 0; -- 건별원화출금
            w_OUT_AMT0     NUMBER(15)   := 0; -- 출고원금
            WACCT_SEQ    VARCHAR2(50)   := ''; -- 계좌일련번호
            WTR_DATE     VARCHAR2(8)    := ''; -- 거래 이체일자
            WTR_DATE_SEQ   NUMBER(10)   := 0; -- 거래일자별일련번호
            wRMN_FAMT      NUMBER(18,2) := 0; -- 거래후 외화잔액
            wRMN_AMT       NUMBER(22)   := 0; -- 거래후 원화잔액
            w_GAP_AMT      NUMBER(15)   := 0; -- 환차
            
            CURSOR c1 is
                select ACCT_SEQ, TR_DATE  , TR_DATE_SEQ, BANK_CD  ,
                       ACNT_NO , EXCH_RATE, RMN_FAMT   , RMN_AMT
                from TN_FORINS
                where BANK_CD = jBANK_CD
                  and ACNT_NO = jACNT_NO
                  and wRMN_FAMT > 0
                order by tr_date, tr_date_seq;
        Begin
            for clr in c1 loop -- 환차익 = 현재평가 - 원금
                w_CNTT := w_CNTT + 1;
                if clr.RMN_FAMT >= w_Fjan then -- 1건으로 처리 완료
                    w_OUTF_AMT := w_Fjan; --외화출금총액
                    w_Fjan     := 0; --잔여 출금 0
                    w_OUT_AMT  := round(w_OUTF_AMT * jEXCH_RATE, 0); --출금 (현재평가가액)
                    w_OUT_AMT0 := round((clr.RMN_AMT / clr.RMN_FAMT) * w_OUTF_AMT, 0); --출고원금
                    w_GAP_AMT := w_OUT_AMT - w_OUT_AMT0; --현재평가가액 - 원금
                else -- 여러건 분할
                    w_OUTF_AMT := clr.RMN_FAMT; --분할된 외화출금액
                    w_Fjan     := w_Fjan - w_OUTF_AMT; --잔여 출금
                    w_OUT_AMT  := round(w_OUTF_AMT * jEXCH_RATE, 0); --출금 (현재평가가액)
                    w_OUT_AMT0 := round((clr.RMN_AMT / clr.RMN_FAMT) * w_OUTF_AMT, 0); --출고원금
                    w_GAP_AMT  := w_OUT_AMT - w_OUT_AMT0; --현재평가가액 - 원금
                end if;

                begin
                    insert into TN_FOROUD (
                        BANK_CD   , ACNT_NO    , TR_DATE     , TR_DATE_SEQ ,
                        ACCT_SEQ  , TR_DATE0   , TR_DATE_SEQ0, MNEY_UNIT   ,
                        OUTF_AMT  , EXCH_RATE  , OUT_AMT     , RMN_FAMT    ,
                        RMN_AMT   , EXCH_RATE0 , OUT_AMT0    , GAP_AMT     ,
                        AC_DATE   , AC_CHITNO  , hang        , UPD_EMP     ,
                        UPD_DATE )
                    values (
                        jBANK_CD     , jACNT_NO     , jTR_DATE       , jTR_DATE_SEQ ,
                        clr.ACCT_SEQ , clr.TR_DATE  , clr.TR_DATE_SEQ, jMNEY_UNIT   ,
                        w_OUTF_AMT   , jEXCH_RATE   , w_OUT_AMT      , clr.RMN_FAMT ,
                        clr.RMN_AMT  , clr.EXCH_RATE, w_OUT_AMT0     , w_GAP_AMT    ,
                        jAC_DATE     , jAC_CHITNO   , w_CNTT         , jUPD_EMP     ,
                        sysdt );
                end;

                if w_Fjan = 0 then
                    goto loop_skip;
                end if;
            end loop;
            <<loop_skip>>
            null;
        end;

        --- 3. 전표 생성
        Declare
            w_CNTT NUMBER(03) := 0; -- 항번
            CURSOR c2 is
                select BANK_CD   ,ACNT_NO    ,TR_DATE      ,TR_DATE_SEQ ,
                       ACCT_SEQ  ,TR_DATE0   ,TR_DATE_SEQ0 ,MNEY_UNIT   ,
                       OUTF_AMT  ,EXCH_RATE  ,OUT_AMT      ,RMN_FAMT    ,
                       RMN_AMT   ,EXCH_RATE0 ,OUT_AMT0     ,GAP_AMT     ,
                       AC_DATE   ,AC_CHITNO  ,HANG         ,UPD_EMP     ,
                       UPD_DATE
                from TN_FOROUD
                where BANK_CD     = jBANK_CD
                  and ACNT_NO     = jACNT_NO
                  and TR_DATE     = jTR_DATE
                  and TR_DATE_SEQ = jTR_DATE_SEQ
                  and GAP_AMT <> 0
                order by tr_date0, tr_date_seq0;
        Begin
            for c2r in c2 loop -- 환차익 = 현재평가 - 원금
                -- 3.1 전표 생성 --------------------------->
                if c2r.GAP_AMT > 0 then --외화예금/ 환차익
                    w_ACNT_CD1 := w_ACNO_ACCT;
                    w_ACNT_CD2 := w_PLUS_ACCT;
                    w_ACNT_NM1 := ft_acnt_nm2(w_ACNT_CD1); -- 외화예금 계정명
                    w_ACNT_NM2 := ft_acnt_nm2(w_ACNT_CD2); -- 환차익 계정명
                else
                    w_ACNT_CD1 := w_MINUS_ACCT;
                    w_ACNT_CD2 := w_ACNO_ACCT;
                    w_ACNT_NM1 := ft_acnt_nm2(w_ACNT_CD1); -- 환차손 계정명
                    w_ACNT_NM2 := ft_acnt_nm2(w_ACNT_CD2); -- 외화예금 계정명
                end if;

                w_HANG := w_HANG + 1;
                w_CHIT_AMT := c2r.GAP_AMT;
                begin
                    insert into TN_BKCHIT (
                           AC_DATE   , AC_CHITNO  , HANG     , DC_FLAG    ,
                           ACNT_CD   , ACNT_NM    , CHIT_AMT , BANK_CD    ,
                           ACNT_NO   , INVOICE_NO , TR_DATE  , TR_DATE_SEQ,
                           MNEY_UNIT , OCCR_PART  , UPD_EMP  , UPD_DATE  )
                   values (
                           jAC_DATE   , jAC_CHITNO   , w_HANG     , '1'         ,
                           w_ACNT_CD1 , w_ACNT_NM1   , w_CHIT_AMT , w_BANK_CD   ,
                           w_ACNT_NO  , w_INVOICE_NO , jTR_DATE   , jTR_DATE_SEQ,
                           w_MNEY_UNIT, w_OCCR_PART  , w_UPD_EMP  , sysdt       );
                end;

                w_HANG := w_HANG + 1;
                begin
                    insert into TN_BKCHIT (
                        AC_DATE   , AC_CHITNO  , HANG     , DC_FLAG    ,
                        ACNT_CD   , ACNT_NM    , CHIT_AMT , BANK_CD    ,
                        ACNT_NO   , INVOICE_NO , TR_DATE  , TR_DATE_SEQ,
                        MNEY_UNIT , OCCR_PART  , UPD_EMP  , UPD_DATE   )
                    values ( 
                        jAC_DATE   , jAC_CHITNO   , w_HANG     , '2'         ,
                        w_ACNT_CD2 , w_ACNT_NM2   , w_CHIT_AMT , w_BANK_CD   ,
                        w_ACNT_NO  , w_INVOICE_NO , jTR_DATE   , jTR_DATE_SEQ,
                        w_MNEY_UNIT, w_OCCR_PART  , w_UPD_EMP  , sysdt       );
                end;
            end loop;

            begin
                update TN_BKCHNO set
                    CHK = nvl(CHK, '0') + 1 -- 전표추가
                where AC_DATE = jAC_DATE
                  and AC_CHITNO = jAC_CHITNO;
            end;
        End;
    END;
    <<end_p>>
    null;
end;
END P_Forout