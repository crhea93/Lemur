#Read input file
#   parameters:
#       input file - .i input file
def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
def read_input_file(input_file,expected_length):
    inputs = {}
    with open(input_file) as f:
        for line in f:
            if '=' in line:
                inputs[line.split("=")[0].strip().lower()] = line.split("=")[1].strip()
            else: pass
        if len(inputs) != expected_length:
            print("Please recheck the input file since some parameter is missing...")
            print("Exiting program...")
            exit()
        else:
            print("Successfully read in input file")
            for key,val in inputs.items():
                if is_number(val) == True and key != 'dir_list':
                    inputs[key] = float(val)
                if key == 'dir_list':
                    #Obtain individual obsids from list
                    obsids = [inputs['dir_list'].split(',')[i].strip() for i in range(len(inputs['dir_list'].split(',')))]
                    inputs['dir_list'] = obsids
        return inputs
