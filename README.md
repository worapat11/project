🐾 Pet Clinic Management System (Academic Edition)

Pet Clinic Management System คือระบบบริหารจัดการคลินิกสัตว์เลี้ยงแบบครบวงจร ที่ถูกออกแบบมาเพื่อรวมศูนย์การทำงานทั้งหมดภายในคลินิก ตั้งแต่การลงทะเบียนเจ้าของสัตว์เลี้ยง การบันทึกประวัติการรักษา (Medical Records) การจัดการนัดหมาย ไปจนถึงการจัดการคลังยาและระบบการชำระเงิน เพื่อเพิ่มประสิทธิภาพในการทำงาน ลดข้อผิดพลาด และสามารถตรวจสอบข้อมูลได้อย่างเป็นระบบ

👥 Meet The Developers (ทีมผู้พัฒนา)
รหัสนักศึกษา	ชื่อ-นามสกุล	
68079454	วรภัทร ดินสวีจิติร	
68024093	ศุภกร นรินทรกุล ณ อยุธยา	
68037232	เนติกร คำสิงหา	

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

⚡ Stored Procedures (Concept Design)
หมายเหตุ: ส่วนนี้เป็นการออกแบบเพื่อการศึกษา 
➕ Add (INSERT)
sp_AddOwner
sp_AddPet
sp_AddAppointment
sp_AddMedicine
sp_AddBill
🔍 Get (SELECT)
sp_GetOwners
sp_GetPets
sp_GetAppointments
sp_GetMedicines
sp_GetBills
✏️ Update
sp_UpdateOwner
sp_UpdatePet
sp_UpdateAppointment
sp_UpdateMedicine
sp_UpdateBill

🤖 Triggers (Concept Design)
หมายเหตุ: ออกแบบเพื่อแสดงแนวคิดการควบคุมข้อมูลในระดับฐานข้อมูล

tr_Owners_Validate
→ ตรวจสอบข้อมูลสำคัญก่อนบันทึก
tr_Medicines_CheckStock
→ ป้องกันปัญหาสต็อกติดลบ
tr_PreventDeleteActivePet
→ ป้องกันการลบข้อมูลที่ยังมีความสัมพันธ์

🔍 Functions & Views (Concept Design)
หมายเหตุ: ใช้เพื่อแสดงแนวคิดการออกแบบ Query ขั้นสูง
Functions
fn_GetPetMedicalHistory → ดึงประวัติการรักษา
fn_CalculateBillTotal → คำนวณยอดรวมค่าใช้จ่าย

Views
vw_BillReport → รายงานบิล
vw_MedicalHistory → ประวัติการรักษา
vw_MedicineStock → สถานะสต็อกยา

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