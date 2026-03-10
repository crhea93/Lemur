#INPUT FILE: All lines starting with # will not be read
#-----Directory Info-----#
home_dir = /home/carterrhea/Documents/Data
web_dir = /home/carterrhea/Documents/Lemur/Web/Cluster_plots
dir_list = 12345,67890
name = ClusterName
#-----Parameter info-----#
redshift = 0.00
#-----Additional Info----#
merge = True
cleaning = False
# API update options
update_api = true
sql_dump_path = /home/carterrhea/Documents/Lemur/Pipeline/Lemur_DB.sql
sqlite_db_path = /home/carterrhea/Documents/Lemur/api/data/lemur.db

# Optional API restart (uvicorn)
api_restart = false
api_health_url = http://localhost:8000/api/health
api_restart_cmd = pkill -f "uvicorn api.app:app" || true; uvicorn api.app:app --reload --host 0.0.0.0 --port 8000 &
