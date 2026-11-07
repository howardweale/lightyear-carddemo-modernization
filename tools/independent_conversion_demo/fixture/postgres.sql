-- Verifier-authored minimal dependencies and synthetic public rows, not upstream DDL.
CREATE TABLE country(country_id integer PRIMARY KEY, country varchar(50));
CREATE TABLE city(city_id integer PRIMARY KEY, city varchar(50), country_id integer);
CREATE TABLE address(address_id integer PRIMARY KEY, address varchar(50), postal_code varchar(10), phone varchar(20), city_id integer);
CREATE TABLE customer(customer_id integer PRIMARY KEY, first_name varchar(45), last_name varchar(45), address_id integer, activebool boolean, store_id integer);
CREATE TABLE staff(staff_id integer PRIMARY KEY, first_name varchar(45), last_name varchar(45));
CREATE TABLE store(store_id integer PRIMARY KEY, address_id integer, manager_staff_id integer);
CREATE TABLE inventory(inventory_id integer PRIMARY KEY, store_id integer);
CREATE TABLE rental(rental_id integer PRIMARY KEY, inventory_id integer);
CREATE TABLE payment(payment_id integer PRIMARY KEY, rental_id integer, amount decimal(10,2));
INSERT INTO country VALUES(1,'Example');
INSERT INTO city VALUES(1,'Same City',1);
INSERT INTO address VALUES(1,'1 Fixture Way','00100','555-0100',1),(2,'2 Fixture Way','00101',NULL,1);
INSERT INTO customer VALUES(1,'Alex','Fixture',1,TRUE,1),(2,'Alex','Fixture',2,FALSE,1);
INSERT INTO staff VALUES(1,'Pat','Manager'),(2,'Pat','Manager');
INSERT INTO store VALUES(1,1,1),(2,2,2);
INSERT INTO inventory VALUES(1,1),(2,2);
INSERT INTO rental VALUES(1,1),(2,2);
INSERT INTO payment VALUES(1,1,1.10),(2,1,2.20),(3,2,4.40),(4,2,0.60);
