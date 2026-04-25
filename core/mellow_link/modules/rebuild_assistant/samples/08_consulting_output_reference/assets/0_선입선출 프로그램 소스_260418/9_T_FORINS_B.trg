CREATE OR REPLACE--9
trigger t_FORINS_B -- 외화입금내역
before insert or update on TN_FORINS
for each row
declare
   wsys_date varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
begin
   :new.RMN_FAMT := nvl(:new.I_FAMT,0) - nvl(:new.O_FSUM, 0); --거래후 외화잔액
   :new.RMN_AMT := nvl(:new.I_AMT,0) - nvl(:new.O_SUM, 0) ; --거래후 원화잔액
   :new.GAP_AMT := nvl(:new.I_AMT,0) - nvl(:new.O_SUM, 0) ; --환차
   if nvl(:new.O_FSUM,0) = 0 then
      :new.AVG_RATE := 0;
   else
      :new.AVG_RATE := round(:new.O_SUM / :new.O_FSUM, 0);
   end if;
end;
