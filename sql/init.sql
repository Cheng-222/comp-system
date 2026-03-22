CREATE TABLE IF NOT EXISTS sys_user (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  real_name VARCHAR(64) NOT NULL,
  mobile VARCHAR(32),
  student_id BIGINT NULL,
  status TINYINT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sys_role (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  role_code VARCHAR(64) NOT NULL UNIQUE,
  role_name VARCHAR(64) NOT NULL,
  status TINYINT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sys_user_role (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  CONSTRAINT fk_sys_user_role_user FOREIGN KEY (user_id) REFERENCES sys_user(id),
  CONSTRAINT fk_sys_user_role_role FOREIGN KEY (role_id) REFERENCES sys_role(id)
);

CREATE TABLE IF NOT EXISTS student_info (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  student_no VARCHAR(32) NOT NULL UNIQUE,
  name VARCHAR(64) NOT NULL,
  gender VARCHAR(16),
  college VARCHAR(128) NOT NULL,
  major VARCHAR(128) NOT NULL,
  class_name VARCHAR(128) NOT NULL,
  grade VARCHAR(32) NULL,
  advisor_name VARCHAR(64) NULL,
  mobile VARCHAR(32),
  email VARCHAR(128),
  history_experience TEXT NULL,
  remark VARCHAR(500) NULL,
  status TINYINT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contest_info (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  contest_name VARCHAR(255) NOT NULL,
  contest_level VARCHAR(64) NOT NULL,
  organizer VARCHAR(255) NOT NULL,
  subject_category VARCHAR(64) NULL,
  undertaker VARCHAR(255) NULL,
  target_students VARCHAR(255) NULL,
  contact_name VARCHAR(64) NULL,
  contact_mobile VARCHAR(32) NULL,
  location VARCHAR(255) NULL,
  description TEXT NULL,
  contest_year INT NULL,
  sign_up_start DATETIME NULL,
  sign_up_end DATETIME NULL,
  contest_date DATETIME NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  material_requirements TEXT NULL,
  quota_limit INT NOT NULL DEFAULT 0,
  rule_attachment_name VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contest_registration (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  contest_id BIGINT NOT NULL,
  student_id BIGINT NOT NULL,
  direction VARCHAR(128),
  team_name VARCHAR(128),
  project_name VARCHAR(255) NULL,
  instructor_name VARCHAR(64) NULL,
  instructor_mobile VARCHAR(32) NULL,
  emergency_contact VARCHAR(64) NULL,
  emergency_mobile VARCHAR(32) NULL,
  source_type VARCHAR(32) NULL,
  remark VARCHAR(500) NULL,
  registration_status VARCHAR(32) NOT NULL DEFAULT 'submitted',
  review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  final_status VARCHAR(32) NOT NULL DEFAULT 'submitted',
  submit_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_registration_contest_student (contest_id, student_id),
  CONSTRAINT fk_registration_contest FOREIGN KEY (contest_id) REFERENCES contest_info(id),
  CONSTRAINT fk_registration_student FOREIGN KEY (student_id) REFERENCES student_info(id)
);

CREATE TABLE IF NOT EXISTS registration_material (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  registration_id BIGINT NOT NULL,
  material_type VARCHAR(64) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  submit_status VARCHAR(32) NOT NULL DEFAULT 'submitted',
  review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  reviewer_id BIGINT NULL,
  review_comment VARCHAR(500) NULL,
  reviewed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_material_registration FOREIGN KEY (registration_id) REFERENCES contest_registration(id),
  CONSTRAINT fk_material_reviewer FOREIGN KEY (reviewer_id) REFERENCES sys_user(id)
);

CREATE TABLE IF NOT EXISTS registration_flow_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  registration_id BIGINT NOT NULL,
  action_type VARCHAR(64) NOT NULL,
  before_status VARCHAR(32),
  after_status VARCHAR(32),
  reason VARCHAR(500),
  operator_id BIGINT NOT NULL,
  operated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_flow_registration FOREIGN KEY (registration_id) REFERENCES contest_registration(id),
  CONSTRAINT fk_flow_operator FOREIGN KEY (operator_id) REFERENCES sys_user(id)
);

CREATE TABLE IF NOT EXISTS notice_message (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  title VARCHAR(255) NOT NULL,
  message_type VARCHAR(32) NOT NULL DEFAULT 'notice',
  target_scope VARCHAR(64) NOT NULL DEFAULT 'all',
  contest_id BIGINT NULL,
  target_role VARCHAR(64) NULL,
  target_status VARCHAR(32) NULL,
  priority VARCHAR(16) NULL,
  summary VARCHAR(255) NULL,
  planned_send_at DATETIME NULL,
  content TEXT NOT NULL,
  send_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  created_by BIGINT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_notice_created_by FOREIGN KEY (created_by) REFERENCES sys_user(id)
);

CREATE TABLE IF NOT EXISTS message_read_record (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  message_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  read_status TINYINT NOT NULL DEFAULT 0,
  read_at DATETIME NULL,
  UNIQUE KEY uq_message_user (message_id, user_id),
  CONSTRAINT fk_read_message FOREIGN KEY (message_id) REFERENCES notice_message(id),
  CONSTRAINT fk_read_user FOREIGN KEY (user_id) REFERENCES sys_user(id)
);

CREATE TABLE IF NOT EXISTS contest_result (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  contest_id BIGINT NOT NULL,
  student_id BIGINT NOT NULL,
  award_level VARCHAR(64),
  result_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  score FLOAT NULL,
  ranking INT NULL,
  certificate_no VARCHAR(64) NULL,
  certificate_attachment_name VARCHAR(255),
  archive_remark VARCHAR(500) NULL,
  confirmed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_result_contest FOREIGN KEY (contest_id) REFERENCES contest_info(id),
  CONSTRAINT fk_result_student FOREIGN KEY (student_id) REFERENCES student_info(id)
);

CREATE TABLE IF NOT EXISTS attachment_info (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  file_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(500) NOT NULL,
  file_ext VARCHAR(32),
  file_size BIGINT NOT NULL DEFAULT 0,
  biz_type VARCHAR(64) NOT NULL,
  uploader_id BIGINT NOT NULL,
  uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_attachment_uploader FOREIGN KEY (uploader_id) REFERENCES sys_user(id)
);

CREATE TABLE IF NOT EXISTS import_task (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_type VARCHAR(64) NOT NULL,
  source_file_id BIGINT NULL,
  success_count INT NOT NULL DEFAULT 0,
  fail_count INT NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  created_by BIGINT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_import_created_by FOREIGN KEY (created_by) REFERENCES sys_user(id)
);

CREATE TABLE IF NOT EXISTS export_task (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_type VARCHAR(64) NOT NULL,
  file_id BIGINT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  created_by BIGINT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_export_created_by FOREIGN KEY (created_by) REFERENCES sys_user(id)
);
