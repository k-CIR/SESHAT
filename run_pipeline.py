import run_config

# Configuration
config = run_config.config_UI()

# Maxfilter
if config['RUN']['Run Maxfilter']:    
    import maxfilter
    mf = maxfilter.MaxFilter(config)
    mf.loop_dirs()