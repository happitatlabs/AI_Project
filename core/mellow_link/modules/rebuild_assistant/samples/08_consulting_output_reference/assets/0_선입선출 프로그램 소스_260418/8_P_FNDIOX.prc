CREATE OR REPLACE--8
procedure P_FNDIOX -- 입금시 가수금전표 생성(입금계좌 계정코드 / 가수금
 (job            in varchar2,
  jacct_seq      in varchar2,
  jtr_date       in varchar2,
  jtr_date_seq   in   number,
  jtr_time       in varchar2,
  jtr_af_date    in varchar2,
  jtr_ipji_gbn   in varchar2,
  jtr_amt        in   number,
  jtr_af_amt     in   number,
  jbr_cd         in varchar2,
  jbr_nm         in varchar2,
  jjukyo         in varchar2,
  jnaeyong       in varchar2,
  jcms_nb        in varchar2,
  jco_reg_nb     in varchar2,
  jco_nm         in varchar2,
  jbank_id       in varchar2,
  jacnt_no       in varchar2,
  jbank_nm       in varchar2,
  jacct_nb       in varchar2,
  jacct_tonghwa  in varchar2,
  jacct_nm       in varchar2,
  jacct_nick     in varchar2,
  jacct_owner_nm in varchar2,
  jlast_upd_date in varchar2,
  jlast_upd_time in varchar2,
  jcnf_yn        in varchar2,
  jadd_yn        in varchar2,
  jacnt_div      in varchar2,
  japp_date      in varchar2,
  japp_type      in varchar2,
  japp_no        in   number,
  jhang          in   number,
  jcms_no        in varchar2,
  jcust_cd       in varchar2,
  jrcv_date      in varchar2,
  jrcv_ser       in   number,
  jrcv_sum       in   number,
  jacnt_unit_cd  in varchar2,
  jac_date       in varchar2,
  jac_chitno     in   number,
  jerp_dtm       in varchar2,
  jback_yn       in varchar2,
  jupd_emp       in varchar2,
  jupd_date      in varchar2)
  is
BEGIN
   DECLARE
      sysdt varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
      w_EXCE_RATE number(17,3) := ft_EXCH_RATE(jtr_date, jacct_tonghwa);
      w_CHIT_AMT number(15) := 0;
      w_OCCR_PART varchar2(08) := '입금';
      w_BANK_CD varchar2(07) := jbank_id; -- 입금은행코드
      w_ACNT_NO varchar2(20) := jacnt_no; -- 입금계좌
      w_ACNO_ACCT varchar2(10) := ''; --ft_acno_acct(w_ACNT_NO); -- 입금계좌의 계정코드
      w_ACNT_CD1 varchar2(10) := w_ACNO_ACCT; -- 입금 계정코드
      w_ACNT_NM1 varchar2(10) := ft_acnt_nm2(w_ACNT_CD1); -- 입금 계정명
      w_ACNT_CD2 varchar2(10) := ft_acnt_cd2('가수금'); -- 가수금 계정코드
      w_ACNT_NM2 varchar2(10) := ft_acnt_nm2(w_ACNT_CD2); -- 가수금 계정명
      w_INVOICE_NO varchar2(50) := jacct_seq; -- INVOICE_NO
      w_MNEY_UNIT varchar2(05) := jacct_tonghwa;
      w_UPD_EMP varchar2(08) := ''; --ft_dept_emp('2221');
   BEGIN -- 차변 : 입금계좌 계정 / 대변 : 가수금
      if ft_dbcheck('T_BKCHIT') = 'INVALID' then
         Raise_Application_Error(-20001, 'T_BKCHIT object INVALID Error');
      end if;

      if nvl(jacct_tonghwa, 'KRW') = 'KRW' then
         w_CHIT_AMT := jtr_amt;
      else
         w_CHIT_AMT := round(w_EXCE_RATE * jtr_amt, 0);
      end if;
      
      begin
         insert into TN_BKCHIT (
                     AC_DATE   , AC_CHITNO  , HANG     , DC_FLAG     ,
                     ACNT_CD   , ACNT_NM    , CHIT_AMT , BANK_CD     ,
                     ACNT_NO   , INVOICE_NO , TR_DATE  , TR_DATE_SEQ ,
                     MNEY_UNIT , OCCR_PART  , UPD_EMP  , UPD_DATE   )
             values (
                     jac_date   , jac_chitno   , 1          , '1'         ,
                     w_ACNT_CD1 , w_ACNT_NM1   , w_CHIT_AMT , w_BANK_CD   ,
                     w_ACNT_NO  , w_INVOICE_NO , jtr_date   , jtr_date_seq,
                     w_MNEY_UNIT, w_OCCR_PART  , w_UPD_EMP  , sysdt      );
      end;
      
      begin
         insert into TN_BKCHIT (
                     AC_DATE   , AC_CHITNO  , HANG     , DC_FLAG     ,
                     ACNT_CD   , ACNT_NM    , CHIT_AMT , BANK_CD     ,
                     ACNT_NO   , INVOICE_NO , TR_DATE  , TR_DATE_SEQ ,
                     MNEY_UNIT , OCCR_PART  , UPD_EMP  , UPD_DATE  )
             values (
                     jac_date   , jac_chitno   , 2          , '2'         ,
                     w_ACNT_CD2 , w_ACNT_NM2   , w_CHIT_AMT , w_BANK_CD   ,
                     w_ACNT_NO  , w_INVOICE_NO , jtr_date   , jtr_date_seq,
                     w_MNEY_UNIT, w_OCCR_PART  , w_UPD_EMP  , sysdt      );
      end;
      
      begin
         update TN_BKCHNO set
                CHK = 'Y'
         where AC_DATE = jac_date
           and AC_CHITNO = jac_chitno;
      end;
   END;
END p_FNDIOX;
      
      
