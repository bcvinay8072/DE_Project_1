# 📊 DE_Project_1: Data Engineering Pipeline with PySpark, MySQL & AWS S3

This project demonstrates an end-to-end Data Engineering pipeline using **PySpark**, **MySQL**, and **AWS S3**, covering ingestion, validation, staging, Data Mart creation, and secure deployment.

---

## 🔐 Environment Variables (`.env`)

```env
AWS_ACCESS_KEY=your-access-key
AWS_SECRET_KEY=your-secret-key
MYSQL_PASSWORD=your-db-password
```

## 🛠 Features

- ✅ Raw Data Ingestion from AWS S3  
- ✅ Validation: Ensures all mandatory fields exist  
- ✅ Error Handling: Moves invalid rows to an S3 error folder  
- ✅ Clean Data Processing: Loads valid data to MySQL  
- ✅ Data Marts:
  - `customers_data_mart`
  - `sales_team_data_mart` (with optional partitioning)  
- ✅ Secure Configuration using `.env`  
- ✅ Local file caching  
- ✅ Reusable modular code  


# 🚀 How to Run
## 1. Set up environment
```
python -m venv .venv
.venv\Scripts\activate        # On Windows
pip install -r requirements.txt
```
## 2. Create .env file in the project root:
```
AWS_ACCESS_KEY=YOUR_KEY
AWS_SECRET_KEY=YOUR_SECRET
MYSQL_PASSWORD=yourpassword
```
## 3. Run the pipeline
```
python src/main/pipeline.py
```
## This will:
- Download the sales file from S3
- Validate and process data
- Move invalid records
- Insert clean data into MySQL
- Create customer and sales data marts

# 🧹 Error Handling
Invalid records (missing columns, nulls) → moved to:
S3 error path: s3://bcvproject-1/sales_data_error/
Local backup path:
C:\Users\bcvpt\OneDrive\Documents\DE Project\error_files\

# 🗃 Output
## ✅ Clean Data → MySQL Tables
- customer
- product
- sales_team
- store
- product_staging_table

## 📈 Data Marts
- customers_data_mart
- sales_team_data_mart

## 🧊 Data Sources
Raw input: s3://bcvproject-1/sales_data_mart/
Customer data mart output: s3://bcvproject-1/customer_data_mart/

## 🧩 Future Enhancements
- Add scheduling with Apache Airflow
- Use SparkSQL for complex transformations
- Push metrics to Prometheus/Grafana
- Integrate with CI/CD using GitHub Actions

## 👨‍💻 Author

**Chenchu Vinay Boga**  
GitHub: [@bcvinay8072](https://github.com/bcvinay8072)

