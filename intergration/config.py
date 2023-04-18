"""
@Description: auto gen system_base.json, module_cfg.cmake, soa_deployment.json, schedule_table.json
@Date: 2023.4.2
"""

import os
import json
import argparse
import re
import linecache

from asw_dir_controller import GEN_FILE_PATH
from asw_dir_controller import REPO_ROOT_PATH

from asw_dir_controller import find_json_files


class CdfJsonParser:
    def __init__(self, paths_file_path):
        self.paths_dict = self._read_paths_file(paths_file_path)
        self.cdf_dict = {}
        self._parse_cdf_json_files()

    def _read_paths_file(self, file_path):
        """读取第一个脚本生成的文件"""
        try:
            with open(file_path, 'r') as f:
                paths_dict = json.load(f)
        except Exception as e:
            print(f'Error reading paths file: {e}')
            raise
        return paths_dict

    def _find_cdf_json_files(self, folder_path):
        """查找指定文件夹下所有的cdf.json文件"""
        cdf_json_files = []
        try:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.endswith("cdf.json"):
                        cdf_json_files.append(os.path.join(root, file))
        except Exception as e:
            print(f'Error finding cdf.json files: {e}')
            raise
        return cdf_json_files

    def _parse_cdf_json_files(self):
        """解析所有cdf.json文件"""
        for items in self.paths_dict:
            path, status = self.paths_dict[items].values()
            if status == True:
                cdf_json_files = self._find_cdf_json_files(path)
                if len(cdf_json_files) == 1:
                    file = cdf_json_files[0]
                    name = os.path.basename(file).replace('_cdf.json', '')
                    with open(file, 'r') as f:
                        try:
                            config = json.load(f)
                        except Exception as e:
                            print(f'Error loading cdf.json file {file}: {e}')
                            raise
                    self.cdf_dict[name] = config
        # print(self.cdf_dict['doorswtfl']['doorswtfl']['Default_Connections'])

    def generate_cmake_file(self, output_path):
        """生成.cmake文件"""
        wr_str = ""
        index = 0
        module_path_list = []
        module_name_list = []
        pattern_str = "\n################ Asw integration ###############"
        # get service path and service name
        for items in self.paths_dict:
            path, status = self.paths_dict[items].values()
            if status == True:
                module_path_list.append('zonal-apps' + path.split('zonal-apps')[-1])
                name = items.split('_cdf.json')[0]
                name = name.replace('-', '_')
                module_name_list.append(name)
        # combine str
        for module in module_path_list:
            index += 1
            temp = "nvos_include_module(NAME \"" + \
                    module_name_list[index - 1] + \
                    "\" TYPE ${NVOS_MOD_TYPE_APP} PATH \"" + \
                    module + \
                    "\")\n"
            wr_str += temp
        # write data
        if output_path:
            open_path = output_path + '/cmake-scripts/module-cfg.cmake'
        else:
            open_path = "./in_cfg/in_module-cfg.cmake"
        try:
            with open(open_path, 'r') as f:
                data = f.read()
            if pattern_str in data:
                index = data.find(pattern_str)
                data = data[:index]
            with open(open_path, 'w') as f:
                f.write(data  + pattern_str + "\n" + wr_str)
        except Exception as e:
            print(f'Error generating module-cfg.cmake file: {e}')
            raise

    def _parse_cdf_instance_and_name(self, path):
        with open(path, 'r') as f:
            data = json.load(f)
        connections = data[next(iter(data.keys()))]["Default_Connections"]
        if connections != []:
            instance = connections[0]['A'].split('.')[0]
        else:
            instance = list(data.keys())[0]
        name = list(data.keys())[0]
        return instance,name

    def generate_base_json_file(self, output_path):
        """生成sytem_base.json文件"""
        attr_list = []
        attr = {}
        # get cdf path and service name
        for items in self.paths_dict:
            path, status = self.paths_dict[items].values()
            if status == True:
                file_list = find_json_files(path)
                for file in file_list:
                    instance,name = self._parse_cdf_instance_and_name(file)
                    attr = {}
                    file = r"${zonal_repo}/" + os.path.relpath(file, REPO_ROOT_PATH + "zonal-apps")
                    attr["Name"] = instance
                    attr["Type"] =  {
                                        "$ref": (file + r"#/" + name)
                                    }
                    attr_list.append(attr)
        # write data
        if output_path:
            open_path = output_path + '/cfg/app_framework/system_base.json'
        else:
            open_path = "./in_cfg/in_system_base.json"
        try:
            with open(open_path, 'r') as f:
                data = json.load(f)
            # remove other service
            remove_list = []
            for module in data["root"]["ComponentInstances"]:
                if r'/platform-apps/' in module["Type"]["$ref"]:
                    remove_list.append(module)
            for module in remove_list:
                data["root"]["ComponentInstances"].remove(module)
            data["root"]["ComponentInstances"] +=  attr_list
            with open(open_path, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f'Error generating sytem_base.json file: {e}')
            raise

    def _parse_cdf_file(self, path):
        with open(path, 'r') as f:
            data = json.load(f)
        return data

    def _get_service_attr(self, data, service_attrs_list):
        server_head = 'SoaM.server_notify_server_status'
        connections = data[next(iter(data.keys()))]["Default_Connections"]
        for connection in connections:
            # if not a service
            if server_head not in connection['B']:
                continue
            attr = {"use_full_service_name": True,
                    "realms": [
                                {
                                    "protocol": "TOX",
                                    "participant": "default"
                                }
                                ],
                    "domain_id": 1
                    }
            if '_ser_' in connection['A']:
                strs = connection['A'].split('_ser_')
                attr["service_name"] = 'ser_' + strs[1]
                if connection['B'].endswith(attr["service_name"]): attr["service_instance_name"] = ''
                else:
                    attr["service_instance_name"] = connection['B'].split(attr["service_name"] + "_") [-1]
                attr["service_package"] = connection['B'].replace(server_head + "_", '').split("_" + attr["service_name"])[0].replace('_', '.')
            else:
                attr["service_name"] = connection['A'].split('_')[-1]
                if connection['B'].endswith(attr["service_name"]): attr["service_instance_name"] = ''
                else:
                    attr["service_instance_name"] = connection['B'].split(attr["service_name"] + "_") [-1]
                attr["service_package"] = connection['B'].replace(server_head + "_", '').split("_" + attr["service_name"])[0].replace('_', '.')
            attr["component_instance_name"] = connection['A'].split('.')[0]
            service_attrs_list.append(attr)

    def _get_client_attr(self, data, client_attrs_list):
        client_head = 'SoaM.client_on_server_status'
        connections = data[next(iter(data.keys()))]["Default_Connections"]
        for connection in connections:
            if client_head not in connection['B']:
                continue
            attr = {"use_full_service_name": True,
                                "participant": "default",
                                "domain_id": 1
                                }
            attr["service_name"] = connection['A'].split('_')[-1]
            if connection['B'].endswith(attr["service_name"]): 
                attr["service_instance_name"] = ''
            else:
                attr["service_instance_name"] = connection['B'].split(attr["service_name"] + "_") [-1]
            attr["component_instance_name"] = connection['A'].split('.')[0]
            name = attr["component_instance_name"]
            attr["service_package"] = connection['B'].replace(client_head + f"_{ name }_", '').split("_" + attr["service_name"])[0].replace('_', '.')
            print(attr["service_package"])
            client_attrs_list.append(attr)
        


    def generate_deploy_json_file(self, output_path):
        """生成deploy.json文件"""
        # get service/client attr
        service_attrs_list = []
        client_attrs_list = []
        for items in self.paths_dict:
            path, status = self.paths_dict[items].values()
            if status == True:
                file_list = find_json_files(path)
                for file in file_list:
                    data = self._parse_cdf_file(file)
                    self._get_service_attr(data, service_attrs_list)
                    self._get_client_attr(data, client_attrs_list)

        # define
        if output_path:
            with open(output_path + '/cfg/soa/soa_deployment.json', 'r') as f:
                data = json.load(f)
        else:
            with open("./in_cfg/soa_deployment.json", 'r') as f:
                data = json.load(f)
        # clear serive client list
        data["services"] = service_attrs_list
        data["clients"] = client_attrs_list
        # add attr to service client
        # write file
        if output_path:
            with open(output_path + '/cfg/soa/soa_deployment.json', 'w') as f:
                json.dump(data, f, indent=4)
        else:
            with open("./in_cfg/soa_deployment.json", 'w') as f:
                json.dump(data, f, indent=4)
    
    def _get_schedule_func(self, folder_path):
        search_line = "/* Exported entry point function */"
        # find .h file
        header_file = ""
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.endswith(".h") and (os.path.basename(folder_path).lower()+".h") == file.lower():
                    header_file = os.path.join(root, file)
                    break
        # find schedule func
        if header_file:
            linecache.checkcache(header_file)
            num_lines = len(linecache.getlines(header_file))
            for i in range(1, num_lines + 1):
                line = linecache.getline(header_file, i)
                if search_line in line:
                    func = linecache.getline(header_file, i+1)
                    return func
            print(f"[Error] {folder_path}")
    
    def _config_schedule_table(self, data, func_list):
        # clear data
        data["schedule_table"]["counter_list"][0]["group_table_list"] = [[]]
        data["schedule_table"]["routine_list"] = [{
                "id": 25,
                "rms_priority": 19,
                "run_time": 1,
                "run_limit_time": 13,
                "handler": "can_scheduler_schedule_table_callback"
            }]
        data["schedule_table"]["schedule_table_list"] = [{
                "name": "schedule_table_can_transmit",
                "sched_mode": "repeating",
                "duration": 1,
                "expiry_points": [
                    {
                        "offset": 0,
                        "task_activations": [25]
                    }
                ]
            }]
        data["schedule_table"]["auto_start"] = [{
                "schedule_table_name": "schedule_table_can_transmit",
                "type": "relative",
                "start_offset": 0
            }]
        #write func
        index = 0
        schd_timer_list = []
        for func in func_list:
            index += 1

            pattern = r"extern void (\w+)_(\d+)ms\(void\);"
            match = re.match(pattern, func)
            if match:
                function_name = match.group(1) + "_" + match.group(2) + "ms"
                time_interval = match.group(2)
            print(function_name)

            routine_temp = {
                "id": 100 + index,
                "rms_priority": 12,
                "run_time": 1,
                "run_limit_time": 10,
                "handler": f"{function_name}"
            }
            data["schedule_table"]["routine_list"].append(routine_temp)
            if time_interval not in schd_timer_list:
                schd_timer_list.append(time_interval)
                schedule_table_temp = {
                    "name": "schedule_table_"+time_interval,
                    "sched_mode": "repeating",
                    "duration": int(time_interval),
                    "expiry_points": [
                        {
                            "offset": 0,
                            "task_activations": [100 + index]
                        }
                    ]
                }
                auto_temp = {
                    "schedule_table_name": "schedule_table_"+time_interval,
                    "type": "relative",
                    "start_offset": 0
                }
                data["schedule_table"]["schedule_table_list"].append(schedule_table_temp)
                data["schedule_table"]["auto_start"].append(auto_temp)
                data["schedule_table"]["counter_list"][0]["group_table_list"][0].append("schedule_table_"+time_interval)
            else:
                num = schd_timer_list.index(time_interval)
                data["schedule_table"]["schedule_table_list"][num+1]["expiry_points"][0]["task_activations"].append(100 + index)
        return data


    def generate_schedule_json_file(self, output_path):
        func_list = []
        for items in self.paths_dict:
            path, status = self.paths_dict[items].values()
            if status == True and self._get_schedule_func(path):
                func_list.append(self._get_schedule_func(path))
        # read json file
        if output_path:
            with open(output_path + '/cfg/code_gen/alps_left1_a/modules/schedule_table.json', 'r') as f:
                data = json.load(f)
        else:
            raise KeyError
            with open("./in_cfg/soa_deployment.json", 'r') as f:
                data = json.load(f)
        # clear serive client list
        data = self._config_schedule_table(data, func_list)
        # add attr to service client
        # write file
        if output_path:
            with open(output_path + '/cfg/code_gen/alps_left1_a/modules/schedule_table.json', 'w') as f:
                json.dump(data, f, indent=4)
        else:
            with open("./in_cfg/soa_deployment.json", 'w') as f:
                json.dump(data, f, indent=4)
        



if __name__ == '__main__':
    # 获取当前目录
    cwd = os.path.dirname(os.path.realpath(__file__))
    # arg parse
    parser = argparse.ArgumentParser(description='arg parse')

    parser.add_argument(
        "--ecu_base",
        required=False,
        help="ecu base path",
    )
    # parser.add_argument(
    #     "--sheet_name",
    #     required=False,
    #     help="set input xlsx page",
    # )
    

    args = parser.parse_args()
    if args.ecu_base:
        args.ecu_base = (REPO_ROOT_PATH) + args.ecu_base
    # print(os.path.abspath(args.ecu_base))

    cdf = CdfJsonParser(GEN_FILE_PATH)
    cdf.generate_base_json_file(args.ecu_base)
    cdf.generate_cmake_file(args.ecu_base)
    cdf.generate_deploy_json_file(args.ecu_base)
    cdf.generate_schedule_json_file(args.ecu_base)
