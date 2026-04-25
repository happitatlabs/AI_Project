create or replace---7
trigger T_FNDIOX -- 가수금 입금 전표 작성 및 입금, 출금 내역 작성
after insert or update or delete on IB_ACCTALL_TR_DD_ADD
for each row
declare
   wcntt            number(05)   := 0;
   wFUND_DEPT_EMP varchar2(10)   := ft_FUND_DEPT_EMP(ft_dept_cd('자금팀')); -- 자금담당자
   sys_dt         varchar2(14)   := to_char(sysdate, 'yyyymmddhh24miss');
   c_rmn_famt       number(17,2) := 0;
   c_rmn_amt        number(15)   := 0;
   c_rmn_avg        number(7,2)  := 0;
   w_EXCH_RATE      number(7,2)  := 0;
   w_FOREIGN_M      number(17,2) := 0;
   w_AVG            number(17,2) := 0;
   w_CHIT_AMT       number(22)   := 0;
   w_AVG_AMT        number(22)   := 0;
   w_GAP_AMT        number(22)   := 0; -- 환차익 (당일환율환산금액-평균환율금액)
   w_RMN_FAMT       number(17,2) := 0;
   w_RMN_AMT        number(22)   := 0;
   w_RMN_AVG        number(17,2) := 0;
   w_LAST_TM      varchar2(20)   := '';
   w_CHIT_RMK     varchar2(200)  := '가수금 입금';
   w_CHG_TIME     varchar2(14)   := :new.TR_DATE||:new.TR_TIME;
BEGIN
   if inserting then -------------((((입력)))) : 1. 가수금전표 생성 후속
      if :new.TR_IPJI_GBN = '1' and nvl(:new.ac_chitno, 0) <> 0 then -- 입금 --> 가수금 전표 생성
         P_FNDIOX('A'               , 
	          :new.acct_seq     , :new.tr_date      , :new.tr_date_seq  , :new.tr_time      ,
                  :new.tr_af_date   , :new.tr_ipji_gbn  , :new.tr_amt       , :new.tr_af_amt    ,
                  :new.br_cd        , :new.br_nm        , :new.jukyo        , :new.naeyong      ,
                  :new.cms_nb       , :new.co_reg_nb    , :new.co_nm        , :new.bank_id      ,
                  :new.ACNT_NO      ,
                  :new.bank_nm      , :new.acct_nb      , :new.ACCT_TONGHWA , :new.acct_nm      ,
                  :new.acct_nick    , :new.acct_owner_nm, :new.last_upd_date, :new.last_upd_time,
                  :new.cnf_yn       , :new.add_yn       , :new.acnt_div     , :new.app_date     ,
                  :new.app_type     , :new.app_no       , :new.hang         , :new.cms_no       ,
                  :new.cust_cd      , :new.rcv_date     , :new.rcv_ser      , :new.rcv_sum      ,
                  :new.acnt_unit_cd , :new.ac_date      , :new.ac_chitno    , :new.erp_dtm      ,
                  :new.back_yn      , wFUND_DEPT_EMP    , sys_dt );
      end if; 

      -- 외화 입출금 기록
      w_EXCH_RATE := ft_EXCH_RATE(:new.tr_date, :new.acct_tonghwa); -- 해당일자의 환율
      w_CHIT_AMT  := round(:new.TR_AMT * w_EXCH_RATE, 0);

      if :new.TR_IPJI_GBN = '1' then -- 입금
         begin
            insert into TN_FORINS (
                        ACCT_SEQ  , TR_DATE   , TR_DATE_SEQ, BANK_CD   ,
                        ACNT_NO   , CHG_TIME  , IO_CD      , MNEY_UNIT ,
                        EXCH_RATE , I_FAMT    , I_AMT      , O_FSUM    ,
                        O_SUM     , GAP_AMT   , AVG_RATE   , CHIT_RMK  ,
                        AC_DATE   , AC_CHITNO , AUTO_YN    , UPD_EMP   ,
                        UPD_DATE )
                values (
                        :new.ACCT_SEQ , :new.TR_DATE , :new.TR_DATE_SEQ, :new.BANK_ID     ,
                        :new.ACNT_NO  , w_CHG_TIME   , :new.TR_IPJI_GBN, :new.ACCT_TONGHWA,
                        w_EXCH_RATE   , :new.TR_AMT  , w_CHIT_AMT      , 0                ,
                        0             , 0            , 0               , w_CHIT_RMK       ,
                        :new.TR_DATE  , 0            , 'N'             , w_CHIT_RMK       ,
                        sys_dt  );
         exception when dup_val_on_index then null;
                   when others then
                        raise_application_error(-20001, '입금내역 입력시 오류 발생'||sqlerrm);
         end;
      else -- 출금
         begin
            insert into TN_FOROUT (
                        BANK_CD   , ACNT_NO   , TR_DATE  , TR_DATE_SEQ,
                        ACCT_SEQ  , MNEY_UNIT , OUTF_AMT , EXCH_RATE  ,
                        OUT_AMT   , OUT_SUM   , GAP_SUM  , AC_DATE    ,
                        AC_CHITNO , UPD_EMP   , UPD_DATE )
                values (
                        :new.BANK_ID , :new.ACNT_NO     , :new.TR_DATE , :new.TR_DATE_SEQ,
                        :new.ACCT_SEQ, :new.ACCT_TONGHWA, :new.TR_AMT  , w_EXCH_RATE     ,
                        w_CHIT_AMT   , 0                , 0            , :new.TR_DATE    ,
                        0            , ''               , sys_dt      ); 
         exception when dup_val_on_index then null;
                   when others then
                        raise_application_error(-20001, '출금내역 입력시 오류 발생'||sqlerrm);
         end;
      end if;

   elsif updating then
      if :new.TR_IPJI_GBN = '1' and nvl(:OLD.ac_chitno, 0) <> 0 and nvl(:new.ac_chitno, 0) = 0 then -- 입금 -->
         p_FNDIOX('D'             , 
	         :old.acct_seq    , :old.tr_date      , :old.tr_date_seq  , :old.tr_time      ,
                 :old.tr_af_date  , :old.tr_ipji_gbn  , :old.tr_amt       , :old.tr_af_amt    ,
                 :old.br_cd       , :old.br_nm        , :old.jukyo        , :old.naeyong      ,
                 :old.cms_nb      , :old.co_reg_nb    , :old.co_nm        , :old.bank_id      ,
	         :old.ACNT_NO     ,
                 :old.bank_nm     , :old.acct_nb      , :old.ACCT_TONGHWA , :old.acct_nm,
                 :old.acct_nick   , :old.acct_owner_nm, :old.last_upd_date, :old.last_upd_time,
                 :old.cnf_yn      , :old.add_yn       , :old.acnt_div     , :old.app_date     ,
	         :old.app_type    , :old.app_no       , :old.hang         , :old.cms_no       ,
                 :old.cust_cd     , :old.rcv_date     , :old.rcv_ser      , :old.rcv_sum      ,
                 :old.acnt_unit_cd, :old.ac_date      , :old.ac_chitno    , :old.erp_dtm      ,
                 :old.back_yn     , wFUND_DEPT_EMP    , sys_dt );
      end if;

      if :old.TR_IPJI_GBN = '1' and nvl(:old.CAN_YN, '0') = '1' and nvl(:new.CAN_YN, '0') = '0' then -- 정상 생성
         P_FNDIOX('A'               , 
	          :new.acct_seq     , :new.tr_date      , :new.tr_date_seq  , :new.tr_time      ,
                  :new.tr_af_date   , :new.tr_ipji_gbn  , :new.tr_amt       , :new.tr_af_amt    ,
                  :new.br_cd        , :new.br_nm        , :new.jukyo        , :new.naeyong      ,
                  :new.cms_nb       , :new.co_reg_nb    , :new.co_nm        , :new.bank_id      ,
                  :new.ACNT_NO      ,
                  :new.bank_nm      , :new.acct_nb      , :new.ACCT_TONGHWA , :new.acct_nm      ,
                  :new.acct_nick    , :new.acct_owner_nm, :new.last_upd_date, :new.last_upd_time,
                  :new.cnf_yn       , :new.add_yn       , :new.acnt_div     , :new.app_date     ,
                  :new.app_type     , :new.app_no       , :new.hang         , :new.cms_no       ,
                  :new.cust_cd      , :new.rcv_date     , :new.rcv_ser      , :new.rcv_sum      ,
                  :new.acnt_unit_cd , :new.ac_date      , :new.ac_chitno    , :new.erp_dtm      ,
                  :new.back_yn      , wFUND_DEPT_EMP    , sys_dt ); 
      end if;
   -- (((삭제)))
   elsif deleting then
      if :new.TR_IPJI_GBN = '1' and nvl(:OLD.ac_chitno, 0) <> 0 and nvl(:new.ac_chitno, 0) = 0 then -- 입금 --> 가수금 전표 삭제
         p_FNDIOX('D'             , 
	         :old.acct_seq    , :old.tr_date      , :old.tr_date_seq  , :old.tr_time      ,
                 :old.tr_af_date  , :old.tr_ipji_gbn  , :old.tr_amt       , :old.tr_af_amt    ,
                 :old.br_cd       , :old.br_nm        , :old.jukyo        , :old.naeyong      ,
                 :old.cms_nb      , :old.co_reg_nb    , :old.co_nm        , :old.bank_id      ,
	         :old.ACNT_NO     ,
                 :old.bank_nm     , :old.acct_nb      , :old.ACCT_TONGHWA , :old.acct_nm,
                 :old.acct_nick   , :old.acct_owner_nm, :old.last_upd_date, :old.last_upd_time,
                 :old.cnf_yn      , :old.add_yn       , :old.acnt_div     , :old.app_date     ,
	         :old.app_type    , :old.app_no       , :old.hang         , :old.cms_no       ,
                 :old.cust_cd     , :old.rcv_date     , :old.rcv_ser      , :old.rcv_sum      ,
                 :old.acnt_unit_cd, :old.ac_date      , :old.ac_chitno    , :old.erp_dtm      ,
                 :old.back_yn     , wFUND_DEPT_EMP    , sys_dt ); 
      end if;

      if :new.TR_IPJI_GBN = '1' then -- 입금
         begin
            delete TN_FORINS
            where ACCT_SEQ = :old.ACCT_SEQ
              and TR_DATE = :old.TR_DATE
              and TR_DATE_SEQ = :old.TR_DATE_SEQ;
         end;
      else -- 출금
         begin
            delete TN_FOROUT
            where BANK_CD = :old.BANK_ID
              and ACNT_NO = :old.ACNT_NO
              and TR_DATE = :old.TR_DATE
              and TR_DATE_SEQ = :old.TR_DATE_SEQ;
         end;
      end if;
   end if;

   -- 최종거래이력--- 최종거래이력
   if inserting or updating then
      begin
         select lpad(to_char(TR_DATE_SEQ), 10, '0')
            into w_LAST_TM
            from IB_ACCTALL_TR_DD_LST
         where TR_DATE = :new.TR_DATE
           and ACCT_NB = :new.ACCT_NB
           and nvl(ACCT_TONGHWA, 'KRW') = nvl(:new.ACCT_TONGHWA, 'KRW')
           and rownum = 1;
      exception when no_data_found then w_LAST_TM := '';
      end;

      if w_LAST_TM < lpad(to_char(:new.TR_DATE_SEQ), 10, '0') then
         begin
            delete IB_ACCTALL_TR_DD_LST
            where TR_DATE = :new.TR_DATE
              and ACCT_NB = :new.ACCT_NB
              and nvl(ACCT_TONGHWA, 'KRW') = nvl(:new.ACCT_TONGHWA, 'KRW');
         end;
    
         begin
            insert into IB_ACCTALL_TR_DD_LST(
                            ACCT_SEQ    , TR_DATE       , TR_DATE_SEQ    , TR_TIME       ,
                            TR_AF_DATE  , TR_IPJI_GBN   , TR_AMT         , TR_AF_AMT     ,
                            BR_CD       , BR_NM         , JUKYO          , NAEYONG       , 
                            CMS_NB      , CO_REG_NB     , CO_NM          , BANK_ID       ,
                            BANK_NM     , ACCT_NB       , ACCT_TONGHWA   , ACCT_NM       ,
                            ACCT_NICK   , ACCT_OWNER_NM , LAST_UPD_DATE  , LAST_UPD_TIME ,
                            CNF_YN      , ADD_YN        , ACNT_DIV       , APP_DATE      ,
                            APP_TYPE    , APP_NO        , HANG           , CMS_NO        ,
                            CUST_CD     , RCV_DATE      , RCV_SER        , RCV_SUM       ,
                            AC_DATE     , AC_CHITNO     , ERP_DTM        , BACK_YN       ,
                            UPD_EMP     , UPD_DATE      , ACNT_UNIT_CD   , OAC_DATE      ,
                            OAC_CHITNO  , CAN_YN        , CAN_EMP        , CAN_TIME      ,
                            CAN_CN      , ACNT_NO       , PAY_UNIT_CD    , PAY_DIV       ,
                            PAY_DATE    , PAY_CHITNO    , PAY_HANG )
                    values (
                            :new.ACCT_SEQ   , :new.TR_DATE      , :new.TR_DATE_SEQ  , :new.TR_TIME      ,
                            :new.TR_AF_DATE , :new.TR_IPJI_GBN  , :new.TR_AMT       , :new.TR_AF_AMT    ,
                            :new.BR_CD      , :new.BR_NM        , :new.JUKYO        , :new.NAEYONG      ,
                            :new.CMS_NB     , :new.CO_REG_NB    , :new.CO_NM        , :new.BANK_ID      ,
                            :new.BANK_NM    , :new.ACCT_NB      , :new.ACCT_TONGHWA , :new.ACCT_NM      ,
                            :new.ACCT_NICK  , :new.ACCT_OWNER_NM, :new.LAST_UPD_DATE, :new.LAST_UPD_TIME,
                            :new.CNF_YN     , :new.ADD_YN       , :new.ACNT_DIV     , :new.APP_DATE     ,
                            :new.APP_TYPE   , :new.APP_NO       , :new.HANG         , :new.CMS_NO       ,
                            :new.CUST_CD    , :new.RCV_DATE     , :new.RCV_SER      , :new.RCV_SUM      ,
                            :new.AC_DATE    , :new.AC_CHITNO    , :new.ERP_DTM      , :new.BACK_YN      ,
                            :new.UPD_EMP    , :new.UPD_DATE     , :new.ACNT_UNIT_CD , :new.OAC_DATE     ,
                            :new.OAC_CHITNO , :new.CAN_YN       , :new.CAN_EMP      , :new.CAN_TIME     ,
                            :new.CAN_CN     , :new.ACNT_NO      , :new.PAY_UNIT_CD  , :new.PAY_DATE     ,
                            :new.PAY_DATE   , :new.PAY_CHITNO   , :new.PAY_HANG     , :new.PAY_DIV
                            );
         exception when others then null;
         end;
      end if;
   end if;
END;
