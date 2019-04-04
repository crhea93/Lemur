'''
Simple python subroutine to read in our specializedf input files
'''
def is_number(s):
    '''
    Check if str is a number. If so return as float
    PARAMETERS:
        s - string
    '''
    try:
        float(s)
        return True
    except ValueError:
        return False
def read_input_file(input_file,expected_length):
    '''
    Read input file
    PARAMETERS:
        input_file - name of input file
        expected_length - number of parameters to read
    '''
    inputs = {}
    with open(input_file) as f:
        #Read file
        for line in f:
            if '=' in line: #Only read lines with '='
                inputs[line.split("=")[0].strip().lower()] = line.split("=")[1].strip()
            else: pass
        if len(inputs) != expected_length: #If we don't have all of our inputs return error and exit
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
            if inputs['merge_name'].lower() == 'none':
                inputs['merge_name'] = inputs['dir_list'][0] #if not merged set merge name to obsid
        return inputs
