import UnityPy
import os

def list_all():
    # Файл дәл осы папкада болғандықтан, атын ғана жазамыз
    file_name = 'data.unity3d'
    
    if not os.path.exists(file_name):
        print(f"Қате: {file_name} табылмады!")
        return

    env = UnityPy.load(file_name)
    found = False
    
    with open('list.txt', 'w') as f:
        for obj in env.objects:
            # Барлық объектілерді тексереміз
            try:
                data = obj.read()
                name = getattr(data, 'name', getattr(data, 'm_Name', ''))
                type_name = obj.type.name
                
                # Тек қана тізімге жазу
                f.write(f"{name} | {type_name} | ID: {obj.path_id}\n")
                found = True
            except:
                continue
                
    if found:
        print("Тізім list.txt файлына сәтті сақталды!")
    else:
        print("Файл ішінен объектілер оқылмады.")

if __name__ == "__main__":
    list_all()

