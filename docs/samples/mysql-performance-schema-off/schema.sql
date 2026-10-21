CREATE DATABASE IF NOT EXISTS demo_shop;
USE demo_shop;

CREATE TABLE customers (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email VARCHAR(255) NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;

CREATE TABLE orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(24) NOT NULL,
  created_at DATETIME NOT NULL,
  total_cents BIGINT NOT NULL,
  PRIMARY KEY (id),
  KEY idx_orders_customer (customer_id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_id BIGINT UNSIGNED NOT NULL,
  product_id BIGINT UNSIGNED NOT NULL,
  quantity INT NOT NULL,
  price_cents INT NOT NULL,
  PRIMARY KEY (id),
  KEY idx_items_order (order_id)
) ENGINE=InnoDB;

DELIMITER //
CREATE PROCEDURE get_customer_order_totals(IN p_customer_id BIGINT UNSIGNED)
BEGIN
  SELECT status, SUM(total_cents) AS total_cents
  FROM orders
  WHERE customer_id = p_customer_id
  GROUP BY status;
END//
DELIMITER ;
