/* Matterfall Launcher.exe: starts the launcher (launcher\matterfall_launcher.pyw) with the Python that
 * ships next to it (python\pythonw.exe), without a console window. Built by tools/package_matterfall.sh. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR arguments, int show)
{
    (void)instance, (void)previous, (void)show;
    static wchar_t dir[32768], python[32768], line[32768];
    DWORD length = GetModuleFileNameW(NULL, dir, 32768);
    if (length == 0 || length >= 32768)
        return 1;
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash)
        *slash = 0;
    swprintf(python, 32768, L"%ls\\python\\pythonw.exe", dir);
    /* Its own arguments go to the launcher ("Matterfall Launcher.exe" --play starts the game at once). */
    swprintf(line, 32768, L"\"%ls\" \"%ls\\launcher\\matterfall_launcher.pyw\" %ls", python, dir,
             arguments ? arguments : L"");

    STARTUPINFOW startup = {.cb = sizeof(startup)};
    PROCESS_INFORMATION process;
    if (!CreateProcessW(python, line, NULL, NULL, FALSE, 0, NULL, dir, &startup, &process)) {
        MessageBoxW(NULL, L"python\\pythonw.exe was not found next to this file. Extract the whole package.",
                    L"Matterfall", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(process.hThread);
    /* Stays until the launcher closes (Steam counts a non-Steam game's time while its program runs). */
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hProcess);
    return (int)code;
}
