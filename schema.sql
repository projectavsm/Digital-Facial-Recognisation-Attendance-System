-- -----------------------------------------------------
-- Digital Facial Recognition Attendance System Schema
-- -----------------------------------------------------

-- 1. Create the database
CREATE DATABASE IF NOT EXISTS attendance_db;
USE attendance_db;

-- 2. Users table
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(50) NOT NULL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    role ENUM('student', 'teacher', 'admin') DEFAULT 'student',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Classes table
CREATE TABLE IF NOT EXISTS classes (
    class_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    class_name VARCHAR(100) NOT NULL,
    teacher_id VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_teacher FOREIGN KEY (teacher_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- 4. Attendance table
CREATE TABLE IF NOT EXISTS attendance (
    attendance_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL,
    class_id INT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status ENUM('present','absent') DEFAULT 'present',

    -- Generated column for date only
    attendance_date DATE AS (DATE(timestamp)) VIRTUAL,

    CONSTRAINT fk_student FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_class FOREIGN KEY (class_id) REFERENCES classes(class_id) ON DELETE CASCADE,
    UNIQUE KEY unique_attendance (student_id, class_id, attendance_date)
);

-- -----------------------------------------------------
-- Optional: Comments for verification
-- SHOW TABLES;
-- SELECT * FROM users;
-- SELECT * FROM classes;
-- DESCRIBE attendance;
-- -----------------------------------------------------
