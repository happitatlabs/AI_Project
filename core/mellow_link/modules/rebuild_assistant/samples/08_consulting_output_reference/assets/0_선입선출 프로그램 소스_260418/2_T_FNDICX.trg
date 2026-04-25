Create or replace
trigger T_FNDICX -- 출금결과 수신시 출금 후 처리
  after insert or UPDATE OR delete on IB_BULK_TRAN_ADD
  for each row
declare
    wcntt            number(05) := 0;
    wFUND_DEPT_EMP varchar2(10) := ft_FUND_DEPT_EMP(ft_dept_cd('재무회계팀')); -- 자금담당자
    sys_dt         varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
BEGIN
---------------------------- (((입력))) ----------------------------
   if inserting then
       if :new.tran_status = '02' and nvl(:new.app_cd, ' ') <> '80' then -- 정상출금 계좌대체 제외
           P_FNDICX('A', :new.TRAN_DT         , :new.TRAN_DT_SEQ      , :new.GROUP_NM        , :new.LIST_NM
                       , :new.LIST_NB         , :new.LIST_NB_SEQ      , :new.TRAN_JI_ACCT_NB , :new.TRAN_IP_BANK_ID
                       , :new.TRAN_IP_ACCT_NB , :new.TRAN_AMT_REQ     , :new.TRAN_AMT        , :new.TRAN_AMT_ERR
                       , :new.TRAN_FEE        , :new.TRAN_REMITTEE_NM , :new.TRAN_JI_NAEYONG , :new.TRAN_IP_NAEYONG
                       , :new.TRAN_CMS_CD     , :new.TRAN_MEMO        , :new.UPCHE_KEY       , :new.TR_DATE
                       , :new.TR_TIME         , :new.TRAN_REG_DATE    , :new.TRAN_REG_TIME   , :new.TRAN_STATUS
                       , :new.TRAN_TYPE_CD    , :new.TRAN_RESULT_CD   , :new.CNF_YN          , :new.REACT_CD
                       , :new.ACNT_DIV        , :new.DEPT_CD          , :new.APP_DATE        , :new.APP_TYPE
                       , :new.APP_NO          , :new.HANG             , :new.ACNT_ORG        , :new.IAC_DATE
                       , :new.IAC_CHITNO      , :new.THANG            , :new.AC_DATE         , :new.AC_CHITNO
                       , :new.BACK_YN         , :new.OUT_BANK_CD      , :new.HOLD_YN         , :new.AUTO_OUT
                       , :new.UPD_EMP         , :new.ACNT_DIV0        , :new.AC_HANG         , :new.ACNT_UNIT_CD
                       , :new.REMARKS         , :new.CUST_CD          , :new.PAY_DATE        , :new.PAY_NO
                       , :new.PAY_STAT        , :new.ACNT_CD2         , :new.PAY_WAY         , :new.PACNT_DIV
                       , :new.RCV_TIME        , :new.RCV_EMP_NO       , :new.FIND_REF_NM     , :new.TR_SYS_GB
                       , :new.ERP_RCV_FLAG    , :new.MNEY_UNIT        , :new.FILE_DATE       , :new.FILE_NUM
                       , :new.FILE_SEQ );
       end if;
   elsif UPDATING then
       if :old.tran_status = '02' AND nvl(:new.tran_status, '00') <> '02' and nvl(:new.APP_CD, ' ') <> '80' then -- 정상출금
           P_FNDICX('D', :old.TRAN_DT         , :old.TRAN_DT_SEQ      , :old.GROUP_NM        , :old.LIST_NM
                       , :old.LIST_NB         , :old.LIST_NB_SEQ      , :old.TRAN_JI_ACCT_NB , :old.TRAN_IP_BANK_ID
                       , :old.TRAN_IP_ACCT_NB , :old.TRAN_AMT_REQ     , :old.TRAN_AMT        , :old.TRAN_AMT_ERR
                       , :old.TRAN_FEE        , :old.TRAN_REMITTEE_NM , :old.TRAN_JI_NAEYONG , :old.TRAN_IP_NAEYONG
                       , :old.TRAN_CMS_CD     , :old.TRAN_MEMO        , :old.UPCHE_KEY       , :old.TR_DATE
                       , :old.TR_TIME         , :old.TRAN_REG_DATE    , :old.TRAN_REG_TIME   , :old.TRAN_STATUS
                       , :old.TRAN_TYPE_CD    , :old.TRAN_RESULT_CD   , :old.CNF_YN          , :old.REACT_CD
                       , :old.ACNT_DIV        , :old.DEPT_CD          , :old.APP_DATE        , :old.APP_TYPE
                       , :old.APP_NO          , :old.HANG             , :old.ACNT_ORG        , :old.IAC_DATE
                       , :old.IAC_CHITNO      , :old.THANG            , :old.AC_DATE         , :old.AC_CHITNO
                       , :old.BACK_YN         , :old.OUT_BANK_CD      , :old.HOLD_YN         , :old.AUTO_OUT
                       , :old.UPD_EMP         , :old.ACNT_DIV0        , :old.AC_HANG         , :old.ACNT_UNIT_CD
                       , :old.REMARKS         , :old.CUST_CD          , :old.PAY_DATE        , :old.PAY_NO
                       , :old.PAY_STAT        , :old.ACNT_CD2         , :old.PAY_WAY         , :old.PACNT_DIV
                       , :old.RCV_TIME        , :old.RCV_EMP_NO       , :old.FIND_REF_NM     , :old.TR_SYS_GB
                       , :old.ERP_RCV_FLAG    , :old.MNEY_UNIT        , :old.FILE_DATE       , :old.FILE_NUM
                       , :old.FILE_SEQ ); 
       end if;
       if :new.tran_status = '02' AND nvl(:old.tran_status, '00') <> '02' and nvl(:new.APP_CD, ' ') <> '80' then -- 정상출금
           P_FNDICX('A', :new.TRAN_DT         , :new.TRAN_DT_SEQ      , :new.GROUP_NM        , :new.LIST_NM
                       , :new.LIST_NB         , :new.LIST_NB_SEQ      , :new.TRAN_JI_ACCT_NB , :new.TRAN_IP_BANK_ID
                       , :new.TRAN_IP_ACCT_NB , :new.TRAN_AMT_REQ     , :new.TRAN_AMT        , :new.TRAN_AMT_ERR
                       , :new.TRAN_FEE        , :new.TRAN_REMITTEE_NM , :new.TRAN_JI_NAEYONG , :new.TRAN_IP_NAEYONG
                       , :new.TRAN_CMS_CD     , :new.TRAN_MEMO        , :new.UPCHE_KEY       , :new.TR_DATE
                       , :new.TR_TIME         , :new.TRAN_REG_DATE    , :new.TRAN_REG_TIME   , :new.TRAN_STATUS
                       , :new.TRAN_TYPE_CD    , :new.TRAN_RESULT_CD   , :new.CNF_YN          , :new.REACT_CD
                       , :new.ACNT_DIV        , :new.DEPT_CD          , :new.APP_DATE        , :new.APP_TYPE
                       , :new.APP_NO          , :new.HANG             , :new.ACNT_ORG        , :new.IAC_DATE
                       , :new.IAC_CHITNO      , :new.THANG            , :new.AC_DATE         , :new.AC_CHITNO
                       , :new.BACK_YN         , :new.OUT_BANK_CD      , :new.HOLD_YN         , :new.AUTO_OUT
                       , :new.UPD_EMP         , :new.ACNT_DIV0        , :new.AC_HANG         , :new.ACNT_UNIT_CD
                       , :new.REMARKS         , :new.CUST_CD          , :new.PAY_DATE        , :new.PAY_NO
                       , :new.PAY_STAT        , :new.ACNT_CD2         , :new.PAY_WAY         , :new.PACNT_DIV
                       , :new.RCV_TIME        , :new.RCV_EMP_NO       , :new.FIND_REF_NM     , :new.TR_SYS_GB
                       , :new.ERP_RCV_FLAG    , :new.MNEY_UNIT        , :new.FILE_DATE       , :new.FILE_NUM
                       , :new.FILE_SEQ ); 
      end if;
   --------------------------((((삭제))))--------------------------
   elsif deleting then
      if :old.tran_status = '02' then -- 정상출금
           P_FNDICX('D', :old.TRAN_DT         , :old.TRAN_DT_SEQ      , :old.GROUP_NM        , :old.LIST_NM
                       , :old.LIST_NB         , :old.LIST_NB_SEQ      , :old.TRAN_JI_ACCT_NB , :old.TRAN_IP_BANK_ID
                       , :old.TRAN_IP_ACCT_NB , :old.TRAN_AMT_REQ     , :old.TRAN_AMT        , :old.TRAN_AMT_ERR
                       , :old.TRAN_FEE        , :old.TRAN_REMITTEE_NM , :old.TRAN_JI_NAEYONG , :old.TRAN_IP_NAEYONG
                       , :old.TRAN_CMS_CD     , :old.TRAN_MEMO        , :old.UPCHE_KEY       , :old.TR_DATE
                       , :old.TR_TIME         , :old.TRAN_REG_DATE    , :old.TRAN_REG_TIME   , :old.TRAN_STATUS
                       , :old.TRAN_TYPE_CD    , :old.TRAN_RESULT_CD   , :old.CNF_YN          , :old.REACT_CD
                       , :old.ACNT_DIV        , :old.DEPT_CD          , :old.APP_DATE        , :old.APP_TYPE
                       , :old.APP_NO          , :old.HANG             , :old.ACNT_ORG        , :old.IAC_DATE
                       , :old.IAC_CHITNO      , :old.THANG            , :old.AC_DATE         , :old.AC_CHITNO
                       , :old.BACK_YN         , :old.OUT_BANK_CD      , :old.HOLD_YN         , :old.AUTO_OUT
                       , :old.UPD_EMP         , :old.ACNT_DIV0        , :old.AC_HANG         , :old.ACNT_UNIT_CD
                       , :old.REMARKS         , :old.CUST_CD          , :old.PAY_DATE        , :old.PAY_NO
                       , :old.PAY_STAT        , :old.ACNT_CD2         , :old.PAY_WAY         , :old.PACNT_DIV
                       , :old.RCV_TIME        , :old.RCV_EMP_NO       , :old.FIND_REF_NM     , :old.TR_SYS_GB
                       , :old.ERP_RCV_FLAG    , :old.MNEY_UNIT        , :old.FILE_DATE       , :old.FILE_NUM
                       , :old.FILE_SEQ );  
      End if;
   End if;
End;