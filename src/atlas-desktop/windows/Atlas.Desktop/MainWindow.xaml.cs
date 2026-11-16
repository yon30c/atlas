using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Atlas.Desktop;

public sealed partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        Navigation.SelectedItem = Navigation.MenuItems[0];
    }

    private void Navigation_SelectionChanged(
        NavigationView sender,
        NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItem is not NavigationViewItem selected)
        {
            return;
        }

        SectionTitle.Text = selected.Content?.ToString() ?? "Atlas";
        SectionStatus.Text = selected.Tag?.ToString() switch
        {
            "Chat" => "La interfaz de conversación está pendiente de un contrato de API disponible.",
            "Conversaciones" => "El historial y su persistencia están pendientes de diseño e implementación.",
            "Conexión" => "La API remota y la vinculación del dispositivo están pendientes.",
            "Configuración" => "Las preferencias de la aplicación están pendientes de diseño.",
            _ => "Sección pendiente."
        };
    }
}
