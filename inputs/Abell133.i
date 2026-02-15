#INPUT FILE: All lines starting with # will not be read
#-----Directory Info-----#
home_dir = /home/carterrhea/Documents/Data/Abell133
#database_password = /home/carterrhea/Documents/db_pass.txt
web_dir = /home/carterrhea/Documents/Lemur/Web/Cluster_plots
dir_list = 2203,9897
name = Abell133
#-----Parameter info-----#
redshift = 0.0566
#-----Additional Info----#
merge = True
cleaning = false
surface_brightness_calc = False

# API update options
update_api = true
sql_dump_path = /home/carterrhea/Documents/Lemur/Pipeline/Lemur_DB.sql
sqlite_db_path = /home/carterrhea/Documents/Lemur/api/data/lemur.db

# Optional API restart (uvicorn)
api_restart = false
api_health_url = http://localhost:8000/api/health
api_restart_cmd = pkill -f "uvicorn api.app:app" || true; uvicorn api.app:app --reload --host 0.0.0.0 --port 8000 &
