-- Verifier-authored negative control; never attributed to the upstream port.
CREATE OR REPLACE VIEW customer_list AS
    SELECT cu.customer_id AS id, (((cu.first_name)::text || ' '::text) || (cu.last_name)::text) AS name, a.address, a.postal_code AS "zip code", a.phone, city.city, country.country, CASE WHEN NOT cu.activebool THEN 'active'::text ELSE ''::text END AS notes, cu.store_id AS sid FROM (((customer cu JOIN address a ON ((cu.address_id = a.address_id))) JOIN city ON ((a.city_id = city.city_id))) JOIN country ON ((city.country_id = country.country_id)));
