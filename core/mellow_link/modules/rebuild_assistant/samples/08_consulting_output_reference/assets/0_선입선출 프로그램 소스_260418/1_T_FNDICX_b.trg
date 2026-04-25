CREATE OR REPLACE trigger t_FNDICX_b -- 출금 완료시 출금전표 번호 생성
before insert or update on IB_BULK_TRAN_ADD
for each row
declare
   wsys_date varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
   w_CHITNO number(04) := 0 ;
   w_CNTT number(05) := 0 ;
   w_OCCR_PART varchar2(08) := '회차';
   w_CHIT_RMK varchar2(200) := '외화출금 환자전표';
   WIF_FILE_KEY varchar2(25) := :new.FILE_DATE||:new.FILE_NUM||:new.FILE_SEQ;
   w_PAY_TM varchar2(14) := nvl(:new.TR_DATE,:new.TRAN_DT)||nvl(:new.TR_TIME,'180000');
begin   
   if (inserting and :new.tran_status = '02') or
      (updating and :new.tran_status = '02' and :old.tran_status <> '02') then -- 정상출금
      if :new.IAC_DATE is null then
         :new.IAC_DATE := :new.TRAN_DT;
      end if;
      w_CHITNO := :new.IAC_CHITNO; --회계전표번호

      if nvl(w_CHITNO,0) = 0 then
         begin
            select max(AC_CHITNO)
               into w_CHITNO
               from TN_BKCHNO
            where AC_DATE = :new.TRAN_DT;
         end;
         <<next_p>>
         w_CHITNO := nvl(w_CHITNO,0) + 1;
         if w_CHITNO > 9999 then
            Raise_Application_Error(-20001, '전표번호 자리수 초과!!!');
         end if;
         begin
            select COUNT(*)
               into w_CNTT
               from TN_BKCHNO
            where AC_DATE = :new.TRAN_DT
              and AC_CHITNO = w_CHITNO;
         end;
         if w_CNTT = 0 then
            begin
               insert into TN_BKCHNO
                           (ac_date ,ac_chitno ,chk ,occr_part ,
                            invoice_no ,TR_DATE ,TR_DATE_SEQ,CHIT_RMK ,
                            ACNT_DIV ,DEPT_CD ,inp_date ,upd_date )
                    values (
		            :new.AC_DATE ,w_CHITNO     ,'0'             ,w_OCCR_PART,
                            WIF_FILE_KEY ,:new.TRAN_DT ,:new.TRAN_DT_SEQ,w_CHIT_RMK,
                            :new.ACNT_DIV,:new.DEPT_CD ,wsys_date       ,wsys_date );
            exception when dup_val_on_index then goto next_p;
            end;
         else
            goto next_p;
         end if;
         :new.IAC_CHITNO := w_CHITNO;
         --- 지급요청 (PAYORD) 에 이체후전표 번호 기재
         begin
            update TN_PAY_ORDER_DTL set -- payord
                   iac_date = :new.IAC_DATE,
                   iac_chitno = w_CHITNO ,
                   PAY_TM = w_PAY_TM
            where AC_DATE = :new.AC_DATE
              and AC_CHITNO = :new.AC_CHITNO
              and AC_HANG = :new.AC_HANG
              and pay_date is not null;
         End;
      End if;
      <<end_p>>
      Null;
   End if;
End;