/* Relocatable CLI: no shell, PATH lookup, external Python or developer tools. */
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char raw[PATH_MAX], executable[PATH_MAX], python[PATH_MAX], worker[PATH_MAX];
    uint32_t size = sizeof(raw);
    if (_NSGetExecutablePath(raw, &size) != 0 || realpath(raw, executable) == NULL) return 126;
    char *slash = strrchr(executable, '/');
    if (!slash) return 126;
    *slash = '\0';
    if (snprintf(python, sizeof(python), "%s/../Resources/Python/bin/python3", executable) >= PATH_MAX ||
        snprintf(worker, sizeof(worker), "%s/../Resources/worker.py", executable) >= PATH_MAX) return 126;
    const char *module = "agent_progress_card";
    int start = 1;
    if (argc > 1) {
        if (strcmp(argv[1], "--wechat") == 0) { module = "agent_progress_wechat.relay"; start = 2; }
        else if (strcmp(argv[1], "--resident") == 0) { module = "agent_progress_wechat.resident"; start = 2; }
        else if (strcmp(argv[1], "--setup") == 0) { module = "agent_progress_card.setup_session"; start = 2; }
    }
    char **arguments = calloc((size_t)argc + 6, sizeof(char *));
    if (!arguments) return 126;
    arguments[0] = python; arguments[1] = "-I"; arguments[2] = "-B";
    arguments[3] = worker; arguments[4] = (char *)module;
    int target = 5;
    for (int index = start; index < argc; index++) arguments[target++] = argv[index];
    execv(python, arguments);
    fputs("Weiguang runtime unavailable. Reinstall the complete application.\n", stderr);
    free(arguments);
    return 126;
}
