CREATE INDEX idx_student_info_student_no ON student_info(student_no);
CREATE INDEX idx_registration_contest_student ON contest_registration(contest_id, student_id);
CREATE INDEX idx_registration_final_status ON contest_registration(final_status);
CREATE INDEX idx_material_registration_id ON registration_material(registration_id);
CREATE INDEX idx_flow_registration_id ON registration_flow_log(registration_id);
CREATE INDEX idx_result_contest_student ON contest_result(contest_id, student_id);
CREATE INDEX idx_notice_send_status ON notice_message(send_status);
