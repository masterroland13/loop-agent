/* Loop Agent window. Blocks until the user closes it. */
#include <gtk/gtk.h>
#include <webkit2/webkit2.h>

static void on_destroy(GtkWidget *widget, gpointer data) {
    (void)widget;
    (void)data;
    gtk_main_quit();
}

int main(int argc, char **argv) {
    const char *url = (argc > 1 && argv[1][0] != '\0') ? argv[1] : "about:blank";

    gtk_init(&argc, &argv);

    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window), "Loop Agent");
    gtk_window_set_default_size(GTK_WINDOW(window), 1280, 800);

    GtkWidget *view = webkit_web_view_new();
    gtk_container_add(GTK_CONTAINER(window), view);
    webkit_web_view_load_uri(WEBKIT_WEB_VIEW(view), url);

    g_signal_connect(window, "destroy", G_CALLBACK(on_destroy), NULL);
    gtk_widget_show_all(window);
    gtk_main();
    return 0;
}
