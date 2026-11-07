SELECT json_build_object('columns',(SELECT json_agg(x) FROM (SELECT column_name AS name,data_type AS type FROM information_schema.columns WHERE table_schema='public' AND table_name='customer_list' ORDER BY ordinal_position) x),
'rows',COALESCE((SELECT json_agg(row_to_json(v)) FROM public.customer_list v),'[]'::json));
