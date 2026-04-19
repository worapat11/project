🐾 Pet Clinic Management System (Academic Edition)

Pet Clinic Management System คือระบบบริหารจัดการคลินิกสัตว์เลี้ยงแบบครบวงจร ที่ถูกออกแบบมาเพื่อรวมศูนย์การทำงานทั้งหมดภายในคลินิก ตั้งแต่การลงทะเบียนเจ้าของสัตว์เลี้ยง การบันทึกประวัติการรักษา (Medical Records) การจัดการนัดหมาย ไปจนถึงการจัดการคลังยาและระบบการชำระเงิน เพื่อเพิ่มประสิทธิภาพในการทำงาน ลดข้อผิดพลาด และสามารถตรวจสอบข้อมูลได้อย่างเป็นระบบ

👥 Meet The Developers (ทีมผู้พัฒนา)
รหัสนักศึกษา	ชื่อ-นามสกุล	
68079454	วรภัทร ดินสวีจิติร	
68024093	ศุภกร นรินทรกุล ณ อยุธยา	
68037232	เนติกร คำสิงหา	

## วิธีใช้งานโปรเจกต์ Django นี้หลังจากดาวน์โหลดจาก GitHub

โปรเจกต์นี้เป็นเว็บไซต์ที่พัฒนาด้วย Django หากต้องการเปิดใช้งานบนเครื่องของคุณ ให้ทำตามขั้นตอนด้านล่าง

---

## สิ่งที่ต้องติดตั้งก่อน
* Python 3.x
* Git (ถ้าจะ clone จาก GitHub)
* VS Code หรือโปรแกรมแก้ไขโค้ดอื่น
* Internet (สำหรับติดตั้ง package)

---

## 1. ดาวน์โหลดโปรเจกต์

### วิธี Clone จาก GitHub

```bash
git clone https://github.com/USERNAME/REPOSITORY.git
```

### หรือดาวน์โหลดเป็น ZIP

* กด Code
* Download ZIP
* แตกไฟล์ออกมา

---

## 2. เข้าโฟลเดอร์โปรเจกต์

```bash
cd project-main
```

---

## 3. สร้าง Virtual Environment

```bash
python -m venv .venv
```

---

## 4. เปิดใช้งาน Virtual Environment

### Windows

```bash
.venv\Scripts\activate
```

### Mac / Linux

```bash
source .venv/bin/activate
```

---

## 5. ติดตั้ง Package ที่จำเป็น

```bash
pip install -r requirements.txt
```

ถ้าไม่มีไฟล์ requirements.txt ให้ติดตั้งเอง เช่น

```bash
pip install django whitenoise python-dateutil
```

---

## 6. Migration Database

สร้างตารางในฐานข้อมูล SQLite เพื่อทำการอัพเดทข้อมูลให้ตรงกัน

```bash
python manage.py migrate
```

---

## 7. สร้าง Admin (ถ้าต้องการ)

```bash
python manage.py createsuperuser
```

แล้วกรอก Username / Email / Password

---

## 8. รันเว็บไซต์

```bash
python manage.py runserver
```

---

## 9. เข้าใช้งานเว็บ

เปิด Browser แล้วเข้า:

```text
http://127.0.0.1:8000/
```

หน้า Admin:

```text
http://127.0.0.1:8000/admin
```

---

## หากรันไม่ได้

### Module not found

ติดตั้ง package เพิ่ม เช่น

```bash
pip install ชื่อแพ็กเกจ
```

### Database Error

ลองรัน

```bash
python manage.py makemigrations
python manage.py migrate
```

### Static file ไม่ขึ้น

รัน

```bash
python manage.py collectstatic
```

---
* ฐานข้อมูลหลักใช้ `db.sqlite3`

---

🚀 Key Features (ฟีเจอร์เด่นของระบบ)
📈 Dashboard

ระบบแดชบอร์ดแสดงภาพรวมข้อมูลภายในคลินิก เช่น สถานะการนัดหมาย รายงานต่าง ๆ และข้อมูลสถิติที่ช่วยให้ผู้ดูแลระบบสามารถติดตามภาพรวมของการดำเนินงานได้อย่างรวดเร็ว

🏥 Clinic Operations Management

ระบบการจัดการภายในคลินิกที่ครอบคลุมทุกกระบวนการ:
🐾 Owner & Pet Management: ลงทะเบียนและจัดการข้อมูลเจ้าของและสัตว์เลี้ยง
📅 Appointment Scheduling: ระบบจัดการนัดหมาย ลดปัญหาการนัดซ้ำซ้อน
📋 Medical Records: บันทึกประวัติการรักษา อาการ วินิจฉัย และวิธีการรักษา
🛍️ POS & Inventory Management

ระบบจัดการสินค้าและคลังยา:

ระบบจัดการคลังยา: ตรวจสอบจำนวนยาและเวชภัณฑ์
Auto Stock Update: ตัดสต็อกอัตโนมัติเมื่อมีการใช้งาน
POS System: บันทึกการขายสินค้าและเชื่อมโยงกับข้อมูลลูกค้า

📊 Reporting System
ระบบรายงานเพื่อการวิเคราะห์:

รายงานสถานะสต็อก
รายงานบัญชีสต็อก
รายงานการนัดหมาย
รายงานสัตว์เลี้ยง
รายงานการชำระเงิน และ POS

🔒 Security
ระบบล็อกอินเข้าสู่ระบบ
การกำหนดสิทธิ์ผู้ใช้งาน (Admin / User)

💾 Core Architecture & SQL Programmability
จุดเด่นของระบบนี้คือการใช้ SQLite เป็นระบบจัดการฐานข้อมูลหลัก ซึ่งเหมาะสำหรับงานในระดับแอปพลิเคชันขนาดเล็กถึงกลาง โดยเน้นความเรียบง่าย พกพาง่าย (Portability) และไม่ต้องติดตั้งเซิร์ฟเวอร์เพิ่มเติม

ภายในระบบมีการออกแบบโครงสร้างฐานข้อมูลแบบ Relational Database อย่างเป็นระบบ และมีการนำตรรกะการทำงานบางส่วนไปจัดการในระดับฐานข้อมูลร่วมกับฝั่งแอปพลิเคชัน เพื่อให้ข้อมูลมีความถูกต้องและลดความซ้ำซ้อนในการทำงาน


📊 Database Design (ERD)
โครงสร้างฐานข้อมูลของระบบถูกออกแบบในรูปแบบ Relational Database โดยมีการกำหนดความสัมพันธ์ของข้อมูลอย่างเป็นระบบตามหลัก Normalization เพื่อลดความซ้ำซ้อนและเพิ่มความถูกต้องของข้อมูล

ตารางหลักที่ใช้ในระบบ ได้แก่:
Owners
Pets
Species
Veterinarians
Appointment
Appointment_Status
Medical_Records
Medicines
Medicine_Stock
Suppliers
Bills
Payment_Method

⚙️ Advanced SQL Design (สำหรับการศึกษาและออกแบบระบบ)
แม้ว่าในระบบ Web Application ที่พัฒนาจริงจะใช้ SQLite และ Application Logic เป็นหลัก
แต่ในส่วนของการออกแบบฐานข้อมูล ได้มีการจำลองการใช้งาน SQL ขั้นสูง เพื่อแสดงแนวคิดการพัฒนาระบบในระดับที่สูงขึ้น และใช้ประกอบการเรียนรู้ทางด้านฐานข้อมูล

🛠️ Technology Stack (Enhanced Version)
Database Management System: SQLite (Lightweight & Embedded Database)
Back-end Logic: SQL Operations ร่วมกับ Database Triggers และ Application Logic
Front-end: HTML5, CSS3, JavaScript
System Type: Web-based Application

✅ จุดเด่นของระบบ
ลดข้อผิดพลาดจากการบันทึกข้อมูลด้วยมือ
เพิ่มความรวดเร็วในการค้นหาข้อมูล
ตรวจสอบข้อมูลย้อนหลังได้ง่าย
ควบคุมคลังยาได้อย่างแม่นยำ
รองรับการทำงานของคลินิกแบบครบวงจร