create or replace
procedure P_FNDICX ( -- 출금 결과에 의한 출금 전표 생성 (제예금단기미지급/출금계좌 계정코드)
   jJOB              in VARCHAR2,
   jTRAN_DT          in VARCHAR2,
   jTRAN_DT_SEQ      in   NUMBER,
   jGROUP_NM         in VARCHAR2,
   jLIST_NM          in VARCHAR2,
   jLIST_NB          in VARCHAR2,
   jLIST_NB_SEQ      in   NUMBER,
   jTRAN_JI_ACCT_NB  in VARCHAR2,
   jTRAN_IP_BANK_ID  in VARCHAR2,
   jTRAN_IP_ACCT_NB  in VARCHAR2,
   jTRAN_AMT_REQ     in   NUMBER,
   jTRAN_AMT         in   NUMBER,
   jTRAN_AMT_ERR     in   NUMBER,
   jTRAN_FEE         in   NUMBER,
   jTRAN_REMITTEE_NM in VARCHAR2,
   jTRAN_JI_NAEYONG  in VARCHAR2,
   jTRAN_IP_NAEYONG  in VARCHAR2,
   jTRAN_CMS_CD      in VARCHAR2,
   jTRAN_MEMO        in VARCHAR2,
   jUPCHE_KEY        in VARCHAR2,
   jTR_DATE          in VARCHAR2,
   jTR_TIME          in VARCHAR2,
   jTRAN_REG_DATE    in VARCHAR2,
   jTRAN_REG_TIME    in VARCHAR2,
   jTRAN_STATUS      in VARCHAR2,
   jTRAN_TYPE_CD     in VARCHAR2,
   jTRAN_RESULT_CD   in VARCHAR2,
   jCNF_YN           in VARCHAR2,
   jREACT_CD         in VARCHAR2,
   jACNT_DIV         in VARCHAR2, -- 전표사업장
   jDEPT_CD          in VARCHAR2,
   jAPP_DATE         in VARCHAR2,
   jAPP_TYPE         in VARCHAR2,
   jAPP_NO           in   NUMBER,
   jHANG             in   NUMBER,
   jACNT_ORG         in VARCHAR2,
   jIAC_DATE         in VARCHAR2,
   jIAC_CHITNO       in   NUMBER,
   jHANG             in   NUMBER,
   jAC_DATE          in VARCHAR2,
   jAC_CHITNO        in   NUMBER,
   jBACK_YN          in VARCHAR2,
   jOUT_BANK_CD      in VARCHAR2,
   jHOLD_YN          in VARCHAR2,
   jAUTO_OUT         in VARCHAR2,
   jUPD_EMP          in VARCHAR2,
   jACNT_DIV0        in VARCHAR2, -- 결의서 사업장
   jAC_HANG          in   NUMBER,
   jACNT_UNIT_CD     in VARCHAR2,
   jREMARKS          in VARCHAR2,
   jCUST_CD          in VARCHAR2,
   jPAY_DATE         in VARCHAR2,
   jPAY_NO           in NUMBER,
   jPAY_STAT         in VARCHAR2,
   jACNT_CD2         in VARCHAR2,
   jPAY_WAY          in VARCHAR2,
   jRACNT_DIV        in VARCHAR2,
   jRCV_TIME         in VARCHAR2,
   jRCV_EMP_NO       in VARCHAR2,
   jFIND_REF_NM      in VARCHAR2,
   jTR_SYS_GB        in VARCHAR2,
   jERP_RCV_FLAG     in VARCHAR2,
   jMONEY_UNIT       in VARCHAR2,
   jFILE_DATE        in VARCHAR2,
   jFILE_NUM         in VARCHAR2,
   jFILE_SEQ         in VARCHAR2
 ) IS
BEGIN
   DECLARE
      sysdt        varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
      w_OCCR_PART  varchar2(08) := '출금';
      w_BANK_CD    varchar2(07) := ft_acno_bank(jTRAN_JI_ACCT_NB); -- 출금은행코드
      w_ACNT_NO    varchar2(20) := jTRAN_JI_ACCT_NB; -- 출금계좌
      w_ACNT_CD1   varchar2(10) := ft_acnt_cd2('미지급금'); -- 미지급금 계정코드
      w_ACNT_NM1   varchar2(10) := ft_acnt_nm2(w_ACNT_CD1); -- 미지급금 계정명
      w_ACNT_CD2   varchar2(10) := ''; -- ft_acno_acct(jTRAN_JI_ACCT_NB); -- 출금계좌 계정코드
      w_ACNT_NM2   varchar2(10) := ft_acnt_nm2(w_ACNT_CD2); -- 출금계좌 계정명
      w_INVOICE_NO varchar2(50) := ''; -- JINVOICE_NO;
      w_MNEY_UNIT  varchar2(05) := 'KRW';
      w_UPD_EMP    varchar2(08) := ''; -- ft_dept_emp('2221');
   BEGIN
      -- 차변 : 미지급금 / 대변 : 출금계좌 계정
      begin
         insert into TN_BKCHIT (
                     AC_DATE   , AC_CHITNO  , HANG     , DC_FLAG    ,
                     ACNT_CD   , ACNT_NM    , CHIT_AMT , BANK_CD    ,
                     ACNT_NO   , INVOICE_NO , TR_DATE  , TR_DATE_SEQ,
                     MNEY_UNIT , OCCR_PART  , UPD_EMP  , UPD_DATE ) 
            values (
                     jIAC_DATE  , jIAC_CHITNO , 1        , '1'         ,
                     w_ACNT_CD1 , w_ACNT_NM1  , pTRAN_AMT, w_BANK_CD   ,
                     w_ACNT_NO  , w_INVOICE_NO, pTRAN_DT , pTRAN_DT_SEQ,
                     w_MNEY_UNIT, w_OCCR_PART , w_UPD_EMP, sysdt  );
      end;
      begin
         insert into TN_BKCHIT (
                     AC_DATE   , AC_CHITNO  , HANG     , DC_FLAG    ,
                     ACNT_CD   , ACNT_NM    , CHIT_AMT , BANK_CD    ,
                     ACNT_NO   , INVOICE_NO , TR_DATE  , TR_DATE_SEQ,
                     MNEY_UNIT , OCCR_PART  , UPD_EMP  , UPD_DATE  )
             values (
                     jIAC_DATE  , jIAC_CHITNO , 2         , '2'         ,
                     w_ACNT_CD2 , w_ACNT_NM2  , pTRAN_AMT , w_BANK_CD   ,
                     w_ACNT_NO  , w_INVOICE_NO, pTRAN_DT  , pTRAN_DT_SEQ,
                     w_MNEY_UNIT, w_OCCR_PART , w_UPD_EMP , sysdt      );
      end;

      begin
         update TN_BKCHNO set
                CHK = '1'
         where AC_DATE   = jIAC_DATE
           and AC_CHITNO = jIAC_CHITNO;
      end;

      <<end_p>>
        null;
   END;
END P_FNDICK;